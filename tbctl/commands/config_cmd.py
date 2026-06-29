import typer

import tbctl.config as cfg

app = typer.Typer(no_args_is_help=True, help="Manage CLI configuration.")


@app.command("set-url")
def set_url(ctx: typer.Context, url: str = typer.Argument(help="ThingsBoard base URL.")):
    profile = ctx.obj["profile"]
    data = cfg.load(profile)
    data["url"] = url
    cfg.save(data, profile)
    typer.echo(f"URL set to {url}")


@app.command("set-token")
def set_token(ctx: typer.Context, token: str = typer.Argument(help="API token.")):
    profile = ctx.obj["profile"]
    data = cfg.load(profile)
    data["token"] = token
    cfg.save(data, profile)
    typer.echo("Token saved.")


@app.command("show")
def show(ctx: typer.Context):
    profile = ctx.obj["profile"]
    data = cfg.load(profile)
    if not data:
        typer.echo(f"No configuration found for profile '{profile}'.")
        return
    for k, v in data.items():
        typer.echo(f"{k} = {v}")
