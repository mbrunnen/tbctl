import ast
import json
import re

import typer

import tb.config as cfg

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _configuration(profile: str):
    try:
        from tb_client.api_client import ApiClient
        from tb_client.configuration import Configuration
    except ImportError:
        typer.echo("tb_client not found. Run ./generate.sh to generate the client.", err=True)
        raise typer.Exit(1)

    conf = cfg.load(profile)
    if not conf.get("url") or not conf.get("token"):
        typer.echo(f"Profile '{profile}' not configured. Run `tb config set-url`.", err=True)
        raise typer.Exit(1)

    configuration = Configuration(host=conf["url"].rstrip("/"))
    configuration.api_key = {"API key form": conf["token"]}
    configuration.api_key_prefix = {"API key form": "ApiKey"}
    return ApiClient(configuration=configuration)


def telemetry_api(profile: str):
    from tb_client.api.telemetry_controller_api import TelemetryControllerApi

    return TelemetryControllerApi(_configuration(profile))


def device_api(profile: str):
    from tb_client.api.device_controller_api import DeviceControllerApi

    return DeviceControllerApi(_configuration(profile))


def device_profile_api(profile: str):
    from tb_client.api.device_profile_controller_api import DeviceProfileControllerApi

    return DeviceProfileControllerApi(_configuration(profile))


def parse_response(value):
    """Coerce a telemetry endpoint response into a list/dict.

    The generated client returns these endpoints as their Python ``repr``
    string (single-quoted, ``True``/``False``), so JSON parsing fails and we
    fall back to ``ast.literal_eval``.
    """
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return ast.literal_eval(value)


def handle_api_error(e):
    from tb_client.exceptions import ApiException

    if isinstance(e, ApiException):
        typer.echo(f"API error {e.status}: {e.reason or e.body}", err=True)
        raise typer.Exit(1)
    raise e


def resolve_device_id(profile: str, device: str) -> str:
    """Return a device UUID, resolving a device name via the tenant lookup."""
    if _UUID_RE.match(device):
        return device
    from tb_client.exceptions import ApiException

    try:
        found = device_api(profile).get_tenant_device(device_name=device)
    except ApiException as e:
        if e.status == 403:
            typer.echo(
                "Device-name lookup needs tenant device-read permission; "
                "pass the device UUID instead.",
                err=True,
            )
            raise typer.Exit(1)
        handle_api_error(e)
    except Exception as e:
        handle_api_error(e)
    if found is None or found.id is None:
        typer.echo(f"Device '{device}' not found.", err=True)
        raise typer.Exit(1)
    return str(found.id.id)
