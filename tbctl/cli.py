import typer

import tbctl.config as cfg
from tbctl.commands import alias, attributes, config_cmd, device, ota, telemetry

app = typer.Typer(no_args_is_help=True)


def complete_profile(incomplete: str) -> list[str]:
    return [p for p in cfg.list_profiles() if p.startswith(incomplete)]


app.add_typer(config_cmd.app, name="config")
app.add_typer(ota.app, name="ota")
app.add_typer(telemetry.app, name="telemetry")
app.add_typer(attributes.app, name="attributes")
app.add_typer(device.app, name="device")
app.add_typer(alias.app, name="alias")


@app.callback()
def callback(
    ctx: typer.Context,
    config: str = typer.Option(
        "default",
        "-c",
        "--config",
        help="Config profile to use.",
        autocompletion=complete_profile,
    ),
):
    ctx.ensure_object(dict)
    ctx.obj["profile"] = config


def main() -> None:
    app()
