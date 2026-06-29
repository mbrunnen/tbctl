import ast
import json
import re

import typer

import tbctl.config as cfg

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

_URI_TEMPLATE_RE = re.compile(r"\{\?[^}]*\}")


def make_api_client(configuration):
    """Build an ApiClient that drops RFC 6570 query-template fragments.

    ThingsBoard's OpenAPI paths embed ``{?param}`` query-expansion templates
    which the generated client leaves verbatim in the request path, yielding
    malformed URLs. Strip them after the client has appended the real query.
    """
    from tb_client.api_client import ApiClient

    class _TbApiClient(ApiClient):
        def param_serialize(self, *args, **kwargs):
            method, url, header_params, body, post_params = super().param_serialize(*args, **kwargs)
            return method, _URI_TEMPLATE_RE.sub("", url), header_params, body, post_params

    return _TbApiClient(configuration=configuration)


def _configuration(profile: str):
    try:
        from tb_client.configuration import Configuration
    except ImportError:
        typer.echo("tb_client not found. Run ./generate.sh to generate the client.", err=True)
        raise typer.Exit(1)

    conf = cfg.load(profile)
    if not conf.get("url") or not conf.get("token"):
        typer.echo(f"Profile '{profile}' not configured. Run `tbctl config set-url`.", err=True)
        raise typer.Exit(1)

    configuration = Configuration(host=conf["url"].rstrip("/"))
    configuration.api_key = {"API key form": conf["token"]}
    configuration.api_key_prefix = {"API key form": "ApiKey"}
    return make_api_client(configuration)


def telemetry_api(profile: str):
    from tb_client.api.telemetry_controller_api import TelemetryControllerApi

    return TelemetryControllerApi(_configuration(profile))


def device_api(profile: str):
    from tb_client.api.device_controller_api import DeviceControllerApi

    return DeviceControllerApi(_configuration(profile))


def owner_api(profile: str):
    from tb_client.api.owner_controller_api import OwnerControllerApi

    return OwnerControllerApi(_configuration(profile))


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


def raw_json(response):
    """Parse a raw client response body, bypassing the generated models.

    The ``Device`` model cannot deserialise ThingsBoard's ``deviceData``: its
    transport configuration is an undiscriminated ``oneOf`` that matches several
    schemas at once. Reading the response as plain JSON sidesteps this. The
    no-preload client path does not raise on error status, so check it here.
    """
    if response.status >= 400:
        from tb_client.exceptions import ApiException

        raise ApiException(http_resp=response)
    return json.loads(response.data)


def raw_get(api, resource_path, query=None):
    """GET a path via the device client and return parsed JSON.

    Used for device-profile lookups: the generated device-profile controller
    cannot be imported (a circular import in its alarm-condition models), so we
    reuse the importable device client's HTTP machinery instead.
    """
    ac = api.api_client
    request = ac.param_serialize(
        method="GET",
        resource_path=resource_path,
        query_params=query or [],
        header_params={"Accept": "application/json"},
        auth_settings=["API key form"],
    )
    response = ac.call_api(*request)
    response.read()
    return raw_json(response)


def resolve_profile_id(profile: str, name: str) -> str:
    api = device_api(profile)
    try:
        if name == "default":
            return raw_get(api, "/api/deviceProfileInfo/default")["id"]["id"]
        page = raw_get(
            api,
            "/api/deviceProfileInfos",
            [("pageSize", 100), ("page", 0), ("textSearch", name)],
        )
    except Exception as e:
        handle_api_error(e)

    matches = [p for p in page.get("data", []) if (p.get("name") or "").lower() == name.lower()]
    if not matches:
        typer.echo(f"Device profile '{name}' not found.", err=True)
        raise typer.Exit(1)
    if len(matches) > 1:
        typer.echo(f"Device profile '{name}' is ambiguous ({len(matches)} matches).", err=True)
        raise typer.Exit(1)
    return matches[0]["id"]["id"]
