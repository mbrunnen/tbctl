import typer

import tb.config as cfg

app = typer.Typer(no_args_is_help=True, help="Manage CLI configuration.")


@app.command("set-url")
def set_url(url: str = typer.Argument(help="ThingsBoard base URL.")):
    data = cfg.load()
    data["url"] = url
    cfg.save(data)
    typer.echo(f"URL set to {url}")


@app.command("set-token")
def set_token(token: str = typer.Argument(help="API token.")):
    data = cfg.load()
    data["token"] = token
    cfg.save(data)
    typer.echo("Token saved.")


@app.command("show")
def show():
    data = cfg.load()
    if not data:
        typer.echo("No configuration found. Run `tb config set-url` and `tb config set-token`.")
        return
    for k, v in data.items():
        typer.echo(f"{k} = {v}")
