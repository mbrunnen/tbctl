import json
import re
import time
from datetime import timezone

import click
import typer

import tbctl.aliases as aliases
from tbctl import keycache
from tbctl.commands._client import (
    handle_api_error,
    parse_response,
    resolve_device_id,
    telemetry_api,
)
from tbctl.commands._format import clip, fmt_ts, fmt_value, ts_header

app = typer.Typer(no_args_is_help=True, help="Read device time-series telemetry.")

_REL_RE = re.compile(r"^(\d+)\s*([smhdw])$", re.IGNORECASE)
_REL_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}

# ThingsBoard applies a server-side default of 100 points when no limit is sent.
# A raw series without --limit is exhausted by paging on the timestamp cursor;
# the aggregation path stays a single request capped at one page.
_PAGE_SIZE = 1_000
_DEFAULT_WINDOW_MS = 24 * 3600 * 1000
_AGGREGATIONS = ["MIN", "MAX", "AVG", "SUM", "COUNT", "NONE"]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_interval(value: str) -> int:
    """Parse an aggregation interval into milliseconds: bare ms or a duration like 5m."""
    value = value.strip()
    if value.isdigit():
        return int(value)
    rel = _REL_RE.match(value)
    if not rel:
        typer.echo("--interval must be milliseconds or a duration like 5m.", err=True)
        raise typer.Exit(1)
    return int(rel.group(1)) * _REL_UNITS[rel.group(2).lower()] * 1000


def _parse_time(value: str, now_ms: int) -> int:
    """Parse a timestamp into epoch milliseconds.

    Accepts epoch milliseconds, a relative offset from now (e.g. '7d', '24h',
    '30m'), or an absolute date/time parsed by dateutil.
    """
    value = value.strip()
    if value.isdigit():
        return int(value)

    rel = _REL_RE.match(value)
    if rel:
        amount, unit = int(rel.group(1)), rel.group(2).lower()
        return now_ms - amount * _REL_UNITS[unit] * 1000

    from dateutil import parser as date_parser

    dt = date_parser.parse(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _plot(result, local: bool) -> None:
    """Render telemetry series as a terminal line chart.

    Skips non-numeric points; exits with an error if no series has numeric data.
    """
    import plotext as plt

    plt.clf()
    plt.date_form("Y-m-d H:M")
    plotted = False
    for key in sorted(result):
        xs, ys = [], []
        for point in result[key] or []:
            try:
                value = float(point.get("value"))
            except (TypeError, ValueError):
                continue
            ys.append(value)
            xs.append(fmt_ts(point["ts"], local)[:16])
        if ys:
            plt.plot(xs, ys, label=key)
            plotted = True

    if not plotted:
        typer.echo("No numeric data points to plot.", err=True)
        raise typer.Exit(1)

    plt.title("Telemetry history")
    plt.show()


@app.command("keys")
def list_keys(
    ctx: typer.Context,
    device: str = typer.Argument(
        help="Device UUID or name.", autocompletion=aliases.complete_device
    ),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    profile = ctx.obj["profile"]
    device_id = resolve_device_id(profile, device)
    try:
        keys = parse_response(telemetry_api(profile).get_timeseries_keys("DEVICE", device_id))
    except Exception as e:
        handle_api_error(e)
    keycache.record(profile, device, device_id, keycache.TIMESERIES, keys, full=True)

    if output_json:
        typer.echo(json.dumps(keys, indent=2, default=str))
        return
    typer.echo("\n".join(sorted(keys)) if keys else "No time-series keys found.")


@app.command("latest")
def latest(
    ctx: typer.Context,
    device: str = typer.Argument(
        help="Device UUID or name.", autocompletion=aliases.complete_device
    ),
    keys: str = typer.Option(
        None,
        "--keys",
        "-k",
        help="Comma-separated telemetry keys.",
        autocompletion=keycache.complete_timeseries_keys,
    ),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
    local: bool = typer.Option(
        False, "--local", help="Show timestamps in local time instead of UTC."
    ),
):
    profile = ctx.obj["profile"]
    device_id = resolve_device_id(profile, device)
    try:
        result = parse_response(
            telemetry_api(profile).get_latest_timeseries("DEVICE", device_id, {}, keys=keys)
        )
    except Exception as e:
        handle_api_error(e)
    keycache.record(profile, device, device_id, keycache.TIMESERIES, result, full=not keys)

    if output_json:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    if not result:
        typer.echo("No telemetry found.")
        return

    from rich.console import Console
    from rich.table import Table

    table = Table(show_header=True, header_style="bold")
    table.add_column("Key")
    table.add_column("Value")
    table.add_column(ts_header("Timestamp", local))
    for key in sorted(result):
        points = result[key] or [{}]
        point = points[0]
        table.add_row(key, fmt_value(point.get("value", "")), fmt_ts(point.get("ts"), local))
    Console().print(table)


def _fetch_series(api, device_id, key, start_ms, end_ms, order):
    """Fetch every point for one key in the window by paging on the timestamp cursor.

    ThingsBoard's ts_kv key is (entity, key, ts), so timestamps are unique per key:
    advancing the cursor past the last returned point loses nothing and repeats nothing.
    """
    points = []
    cursor = start_ms
    while True:
        page = parse_response(
            api.get_timeseries(
                "DEVICE",
                device_id,
                cursor,
                end_ms,
                {},
                keys=key,
                limit=str(_PAGE_SIZE),
                order_by="ASC",
            )
        )
        batch = page.get(key) or []
        points.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        cursor = batch[-1]["ts"] + 1
    if order.upper() == "DESC":
        points.reverse()
    return points


@app.command("history")
def history(
    ctx: typer.Context,
    device: str = typer.Argument(
        help="Device UUID or name.", autocompletion=aliases.complete_device
    ),
    keys: str = typer.Option(
        None,
        "--keys",
        "-k",
        help="Comma-separated telemetry keys (default: all keys).",
        autocompletion=keycache.complete_timeseries_keys,
    ),
    start: str = typer.Option(
        None, "--start", help="Start time: epoch ms, ISO date, or offset like 7d."
    ),
    end: str = typer.Option(None, "--end", help="End time: epoch ms or ISO date (default: now)."),
    last: str = typer.Option(
        None,
        "--last",
        help="Window ending now, e.g. 7d, 24h, 30m; a bare count means the newest N points "
        "(default: 24h).",
    ),
    limit: int = typer.Option(
        None, "--limit", help="Max data points per key (default: fetch the full window)."
    ),
    order: str = typer.Option(
        "ASC",
        "--order",
        help="Sort order.",
        metavar="[ASC|DESC]",
        click_type=click.Choice(["ASC", "DESC"], case_sensitive=False),
    ),
    agg: str = typer.Option(
        None,
        "--agg",
        help="Aggregation function.",
        metavar=f"[{'|'.join(_AGGREGATIONS)}]",
        click_type=click.Choice(
            ["MIN", "MAX", "AVG", "SUM", "COUNT", "NONE"], case_sensitive=False
        ),
    ),
    interval: str = typer.Option(
        None, "--interval", help="Aggregation interval: milliseconds or a duration like 5m, 1h."
    ),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
    plot: bool = typer.Option(False, "--plot", help="Render a terminal line chart."),
    local: bool = typer.Option(
        False, "--local", help="Show timestamps in local time instead of UTC."
    ),
):
    if plot and output_json:
        typer.echo("--plot and --json are mutually exclusive.", err=True)
        raise typer.Exit(1)
    interval_ms = _parse_interval(interval) if interval else None

    now_ms = _now_ms()
    count = None
    if last and last.strip().isdigit():
        count = int(last)
        if count < 1:
            typer.echo("--last needs a positive count, e.g. --last 20.", err=True)
            raise typer.Exit(1)
        if limit is not None or agg:
            typer.echo(
                f"--last {count} already asks for the {count} newest points and cannot be "
                "combined with --limit or --agg; pass a window like 20d instead.",
                err=True,
            )
            raise typer.Exit(1)
        start_ms, end_ms = 0, now_ms
    elif last:
        start_ms = _parse_time(last, now_ms)
        end_ms = now_ms
    else:
        end_ms = _parse_time(end, now_ms) if end else now_ms
        start_ms = _parse_time(start, now_ms) if start else end_ms - _DEFAULT_WINDOW_MS

    profile = ctx.obj["profile"]
    device_id = resolve_device_id(profile, device)
    api = telemetry_api(profile)
    full = not keys
    try:
        if full:
            all_keys = parse_response(api.get_timeseries_keys("DEVICE", device_id))
            keycache.record(profile, device, device_id, keycache.TIMESERIES, all_keys, full=True)
            keys = ",".join(all_keys)
        if not keys:
            result = {}
        elif count:
            # Ask the server for the tail, then restore the requested display order.
            result = parse_response(
                api.get_timeseries(
                    "DEVICE",
                    device_id,
                    start_ms,
                    end_ms,
                    {},
                    keys=keys,
                    limit=str(count),
                    order_by="DESC",
                )
            )
            if order.upper() != "DESC":
                for key in result:
                    (result[key] or []).reverse()
        elif limit is None and not agg:
            result = {}
            for key in (k.strip() for k in keys.split(",") if k.strip()):
                points = _fetch_series(api, device_id, key, start_ms, end_ms, order)
                if points:
                    result[key] = points
        else:
            effective_limit = limit if limit is not None else _PAGE_SIZE
            result = parse_response(
                api.get_timeseries(
                    "DEVICE",
                    device_id,
                    start_ms,
                    end_ms,
                    {},
                    keys=keys,
                    limit=str(effective_limit),
                    agg=agg,
                    interval=interval_ms,
                    order_by=order,
                )
            )
            if any(len(result[key] or []) >= effective_limit for key in result):
                typer.echo(
                    f"Reached the limit of {effective_limit} points per key; "
                    "results may be truncated. Increase --limit to fetch more.",
                    err=True,
                )
    except Exception as e:
        handle_api_error(e)
    if not full:
        keycache.record(profile, device, device_id, keycache.TIMESERIES, result, full=False)

    if output_json:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    if not result:
        typer.echo("No telemetry found in the given range.")
        return

    if plot:
        _plot(result, local)
        return

    from rich.console import Console
    from rich.table import Table

    keys = sorted(result)
    rows: dict[int, dict] = {}
    for key in keys:
        for point in result[key] or []:
            rows.setdefault(point["ts"], {})[key] = point.get("value", "")
    table = Table(show_header=True, header_style="bold")
    table.add_column(ts_header("Timestamp", local), no_wrap=True)
    for key in keys:
        table.add_column(key)
    for ts in sorted(rows, reverse=order == "DESC"):
        row = rows[ts]
        table.add_row(
            fmt_ts(ts, local), *(clip(fmt_value(row[k])) if k in row else "" for k in keys)
        )
    Console().print(table)
