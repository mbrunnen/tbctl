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


def _get_api():
    try:
        from tb_client.api.ota_package_controller_api import OtaPackageControllerApi
        from tb_client.api_client import ApiClient
        from tb_client.configuration import Configuration
    except ImportError:
        typer.echo("tb_client not found. Run ./generate.sh to generate the client.", err=True)
        raise typer.Exit(1)

    conf = cfg.load()
    if not conf.get("url") or not conf.get("token"):
        typer.echo("Not configured. Run `tb config set-url` and `tb config set-token`.", err=True)
        raise typer.Exit(1)

    configuration = Configuration(host=conf["url"])
    configuration.api_key = {"X-Authorization": f"ApiKey {conf['token']}"}
    return OtaPackageControllerApi(ApiClient(configuration=configuration))


@app.command("list")
def list_packages(
    page_size: int = typer.Option(20, "--page-size", help="Packages per page."),
):
    from rich.console import Console
    from rich.table import Table

    api = _get_api()
    result = api.get_ota_packages(page_size=page_size, page=0)

    if not result.data:
        typer.echo("No OTA packages found.")
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
def get_package(id: str = typer.Argument(help="OTA package UUID.")):
    api = _get_api()
    pkg = api.get_ota_package_info_by_id(ota_package_id=id)
    typer.echo(json.dumps(pkg.to_dict(), indent=2, default=str))


@app.command("delete")
def delete_package(
    id: str = typer.Argument(help="OTA package UUID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
):
    if not yes:
        typer.confirm(f"Delete OTA package {id}?", abort=True)
    api = _get_api()
    api.delete_ota_package(ota_package_id=id)
    typer.echo(f"Deleted {id}")
