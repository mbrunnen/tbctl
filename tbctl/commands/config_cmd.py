import json

import typer

import tbctl.config as cfg
import tbctl.credentials as credentials
from tbctl import session

app = typer.Typer(no_args_is_help=True, help="Show CLI configuration.")


def _flatten(data: dict, prefix: str = ""):
    """Yield ``(dotted-key, value)`` pairs so nested tables print one per line."""
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _flatten(value, f"{path}.")
        else:
            yield path, value


@app.command("show")
def show(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    profile = ctx.obj["profile"]
    stored = cfg.load(profile)
    data = {key: stored[key] for key in ("url", "aliases") if key in stored}
    cred = credentials.load(profile)
    if not data and not cred:
        typer.echo("{}" if output_json else f"No configuration found for profile '{profile}'.")
        return
    data["auth"] = cred.kind if cred else "not set"
    if cred:
        data["source"] = cred.source
    if cred and cred.source != credentials.ENV and "refresh_expires" in stored:
        data["refresh_expires"] = session.date(stored["refresh_expires"])
    if output_json:
        typer.echo(json.dumps(data, indent=2))
        return
    for key, value in _flatten(data):
        typer.echo(f"{key} = {value}")
