import typer

from tb.commands import config_cmd, ota

app = typer.Typer(no_args_is_help=True)
app.add_typer(config_cmd.app, name="config")
app.add_typer(ota.app, name="ota")


def main() -> None:
    app()
