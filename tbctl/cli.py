from enum import Enum

import typer
from typer._completion_shared import get_completion_script

import tbctl.config as cfg
from tbctl.commands import alias, attributes, auth, config_cmd, device, ota, telemetry

app = typer.Typer(no_args_is_help=True)


def complete_profile(incomplete: str) -> list[str]:
    return [p for p in cfg.list_profiles() if p.startswith(incomplete)]


app.add_typer(auth.app, name="auth")
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


class Shell(str, Enum):
    bash = "bash"
    zsh = "zsh"
    fish = "fish"
    powershell = "powershell"
    pwsh = "pwsh"


@app.command("completion")
def completion(shell: Shell = typer.Argument(help="Shell to generate the script for.")):
    """Print the completion script for SHELL."""
    typer.echo(
        get_completion_script(prog_name="tbctl", complete_var="_TBCTL_COMPLETE", shell=shell.value)
    )


def main() -> None:
    app()
