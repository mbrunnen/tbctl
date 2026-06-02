import json

import typer

import tb.config as cfg

app = typer.Typer(no_args_is_help=True, help="Manage OTA packages.")


def _format_size(size_bytes) -> str:
    if size_bytes is None:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024**2:.1f} MB"


def _get_api(profile: str):
    try:
        from tb_client.api.ota_package_controller_api import OtaPackageControllerApi
        from tb_client.api_client import ApiClient
        from tb_client.configuration import Configuration
    except ImportError:
        typer.echo("tb_client not found. Run ./generate.sh to generate the client.", err=True)
        raise typer.Exit(1)

    conf = cfg.load(profile)
    if not conf.get("url") or not conf.get("token"):
        typer.echo(f"Profile '{profile}' not configured. Run `tb config set-url`.", err=True)
        raise typer.Exit(1)

    configuration = Configuration(host=conf["url"])
    configuration.api_key = {"API key form": conf["token"]}
    configuration.api_key_prefix = {"API key form": "ApiKey"}
    return OtaPackageControllerApi(ApiClient(configuration=configuration))


def _handle_api_error(e):
    from tb_client.exceptions import ApiException

    if isinstance(e, ApiException):
        typer.echo(f"API error {e.status}: {e.reason or e.body}", err=True)
        raise typer.Exit(1)
    raise e


@app.command("list")
def list_packages(
    ctx: typer.Context,
    page_size: int = typer.Option(20, "--page-size", help="Packages per page."),
    text_search: str = typer.Option(None, "--search", "-s", help="Substring filter on title."),
    device_profile_id: str = typer.Option(
        None, "--device-profile", "-d", help="Filter by device profile UUID."
    ),
    type: str = typer.Option(None, "--type", "-t", help="Filter by type: FIRMWARE or SOFTWARE."),
    sort_property: str = typer.Option(None, "--sort-by", help="Property to sort by."),
    sort_order: str = typer.Option(None, "--sort-order", help="ASC or DESC."),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    from rich.console import Console
    from rich.table import Table

    if bool(device_profile_id) != bool(type):
        typer.echo("--device-profile and --type must be used together.", err=True)
        raise typer.Exit(1)

    api = _get_api(ctx.obj["profile"])
    try:
        if device_profile_id and type:
            result = api.get_ota_packages1(
                device_profile_id=device_profile_id,
                type=type,
                page_size=page_size,
                page=0,
                text_search=text_search,
                sort_property=sort_property,
                sort_order=sort_order,
            )
        else:
            result = api.get_ota_packages(
                page_size=page_size,
                page=0,
                text_search=text_search,
                sort_property=sort_property,
                sort_order=sort_order,
            )
    except Exception as e:
        _handle_api_error(e)

    if not result.data:
        typer.echo("[]" if output_json else "No OTA packages found.")
        return

    if output_json:
        typer.echo(json.dumps([pkg.to_dict() for pkg in result.data], indent=2, default=str))
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Version")
    table.add_column("Type")
    table.add_column("Size", justify="right")

    for pkg in result.data:
        pkg_id = str(pkg.id.id) if pkg.id is not None else ""
        table.add_row(
            pkg_id,
            pkg.title or "",
            pkg.version or "",
            pkg.type or "",
            _format_size(getattr(pkg, "data_size", None)),
        )

    console = Console()
    console.print(table)
    console.print(f"Showing {len(result.data)} of {result.total_elements} packages")


@app.command("get")
def get_package(ctx: typer.Context, id: str = typer.Argument(help="OTA package UUID.")):
    api = _get_api(ctx.obj["profile"])
    try:
        pkg = api.get_ota_package_info_by_id(ota_package_id=id)
    except Exception as e:
        _handle_api_error(e)
    typer.echo(json.dumps(pkg.to_dict(), indent=2, default=str))


@app.command("delete")
def delete_package(
    ctx: typer.Context,
    id: str = typer.Argument(help="OTA package UUID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
):
    if not yes:
        typer.confirm(f"Delete OTA package {id}?", abort=True)
    api = _get_api(ctx.obj["profile"])
    try:
        api.delete_ota_package(ota_package_id=id)
    except Exception as e:
        _handle_api_error(e)
    typer.echo(f"Deleted {id}")
