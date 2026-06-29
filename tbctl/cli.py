import typer

from tbctl.commands import attributes, config_cmd, device, ota, telemetry

app = typer.Typer(no_args_is_help=True)
app.add_typer(config_cmd.app, name="config")
app.add_typer(ota.app, name="ota")
app.add_typer(telemetry.app, name="telemetry")
app.add_typer(attributes.app, name="attributes")
app.add_typer(device.app, name="device")


@app.callback()
def callback(
    ctx: typer.Context,
    config: str = typer.Option("default", "-c", "--config", help="Config profile to use."),
):
    ctx.ensure_object(dict)
    ctx.obj["profile"] = config


def main() -> None:
    app()
