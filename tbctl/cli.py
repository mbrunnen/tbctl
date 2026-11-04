from enum import Enum

import typer
from typer._completion_shared import get_completion_script

import tbctl.config as cfg
from tbctl.commands import alias, attributes, auth, config_cmd, device, ota, telemetry

app = typer.Typer(no_args_is_help=True)


def complete_context(ctx, incomplete: str) -> list[str]:
    try:
        path, _ = cfg.config_file((ctx.params or {}).get("config"))
        names = cfg.contexts(cfg.read(path))
    except Exception:
        return []
    return [name for name in names if name.startswith(incomplete)]


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
    config: str = typer.Option(None, "-c", "--config", help="Config file."),
    context: str = typer.Option(
        None, "--context", help="Context in the config file.", autocompletion=complete_context
    ),
):
    ctx.ensure_object(dict)


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
