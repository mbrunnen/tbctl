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


def build_client(url: str, token: str):
    from tb_client.configuration import Configuration

    configuration = Configuration(host=url.rstrip("/"))
    configuration.api_key = {"API key form": token}
    configuration.api_key_prefix = {"API key form": "ApiKey"}
    return make_api_client(configuration)


def _configuration(profile: str):
    try:
        from tb_client.configuration import Configuration  # noqa: F401
    except ImportError:
        typer.echo("tb_client not found. Run ./generate.sh to generate the client.", err=True)
        raise typer.Exit(1)

    conf = cfg.load(profile)
    if not conf.get("url") or not conf.get("token"):
        typer.echo(f"Profile '{profile}' not configured. Run `tbctl config set-url`.", err=True)
        raise typer.Exit(1)

    return build_client(conf["url"], conf["token"])


def check_connection(url: str, token: str) -> tuple[bool, str]:
    """Verify a URL and token against /api/auth/user without ever raising."""
    try:
        from tb_client.exceptions import ApiException
    except ImportError:
        return False, "tb_client not found; run ./generate.sh"

    try:
        user = raw_get(build_client(url, token), "/api/auth/user")
    except ApiException as e:
        return False, f"{e.status} {e.reason or ''}".strip()
    except Exception as e:
        return False, str(e)
    return True, user.get("email", "")


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


def _error_detail(e):
    """Pull ThingsBoard's human-readable ``message`` out of an error body."""
    if e.body:
        try:
            return json.loads(e.body).get("message") or e.body
        except (json.JSONDecodeError, ValueError, AttributeError):
            return e.body
    return e.reason


def handle_api_error(e):
    from tb_client.exceptions import ApiException

    if isinstance(e, ApiException):
        typer.echo(f"Error {e.status}: {_error_detail(e)}", err=True)
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
    ac = getattr(api, "api_client", api)
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


def raw_post(api, resource_path, body):
    """POST a plain-dict JSON body and return parsed JSON.

    Several generated request models serialise to an empty body: their
    ``to_dict`` excludes every payload field. Sending a hand-built dict through
    the client's HTTP machinery sidesteps those models entirely.
    """
    ac = getattr(api, "api_client", api)
    request = ac.param_serialize(
        method="POST",
        resource_path=resource_path,
        body=body,
        header_params={"Accept": "application/json", "Content-Type": "application/json"},
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


def _save_device_raw(api, body):
    """Save a device from a plain dict, bypassing the Device model.

    The generated Device model both fails to import cleanly (circular import)
    and cannot round-trip ``deviceData`` (undiscriminated ``oneOf``). Building a
    plain dict and serialising it through the endpoint's own request builder
    avoids the model entirely on both the request and response sides.
    """
    request = api._save_device_serialize(
        device=body,
        access_token=None,
        entity_group_id=None,
        entity_group_ids=None,
        name_conflict_policy=None,
        uniquify_separator=None,
        uniquify_strategy=None,
        _request_auth=None,
        _content_type=None,
        _headers=None,
        _host_index=0,
    )
    response = api.api_client.call_api(*request)
    response.read()
    return raw_json(response)
