# Interactive config wizard: `tbctl config init`

## Problem

First-time setup requires two separate commands (`config set-url`, `config
set-token`) and gives no feedback on whether the URL and token actually work.
Users only discover a wrong URL or invalid token when a later command fails with
an opaque API error. An interactive wizard collects both values in one guided
flow and verifies them against the server before saving.

## Scope

A single new subcommand, `tbctl config init`, plus a small refactor of the
client-building helpers so the wizard can validate credentials without
duplicating that logic. No change to `set-url`, `set-token`, or `show`.

## Command

```
tbctl [-c PROFILE] config init
```

Operates on the profile from the CLI context (`ctx.obj["profile"]`), exactly
like every other command. Running with `-c staging` configures the `staging`
profile.

## Flow

1. Load the existing profile config (may be empty).
2. **URL prompt** — `typer.prompt("ThingsBoard URL", default=existing_url)`.
   When a URL already exists it is offered as the default; pressing Enter keeps
   it. When none exists the prompt has no default and requires input.
3. **Token prompt** — hidden input (`hide_input=True`).
   - No existing token: token is required.
   - Existing token: the prompt indicates the current token is kept on empty
     input, and an empty answer keeps the stored token (the secret is never
     echoed as a default).
4. **Validate** — build a client from the just-entered url + token and call
   `GET /api/auth/user`.
   - Success: print `Connection OK (logged in as <email>)`.
   - Failure: print `Warning: could not verify credentials: <reason>`.
   - Either way, continue to save.
5. **Save** the url + token to the profile TOML and print a confirmation line.

## Refactor: `tbctl/commands/_client.py`

Extract the client-building block so it can be driven from explicit values
rather than only from saved config:

- `build_client(url, token)` — the `Configuration` + `make_api_client` block
  currently inside `_configuration`. `_configuration` loads the saved config,
  validates presence of url/token, then delegates to `build_client`.
- `check_connection(url, token) -> tuple[bool, str]` — builds a client via
  `build_client`, performs `raw_get(..., "/api/auth/user")`, and returns
  `(True, email)` on success or `(False, reason)` on failure. It catches
  `ApiException` and connection errors and never raises, so the wizard can warn
  and continue.

`GET /api/auth/user` is chosen because it is the cheapest authenticated
"who am I" call and confirms both URL reachability and token validity
regardless of the token's role (a device-scoped call could 403 on a valid but
low-privilege token). It is reached via `raw_get` rather than the generated
`AuthControllerApi`, matching how other endpoints avoid the generated models'
`oneOf` deserialisation issues.

## Error handling

- Validation failures never abort the wizard: the user may be offline or the
  server temporarily down, and the values may still be correct.
- Missing generated client (`tb_client` import fails) surfaces the existing
  "Run ./generate.sh" message via the shared helper path.

## Testing

pytest + `CliRunner`, using the `config_dir` fixture and `input=` to drive the
prompts. `check_connection` is monkeypatched so no test touches the network.

- writes url + token to the correct profile TOML;
- token entry is hidden and an empty token on re-run keeps the existing one;
- the existing URL is offered as the default on re-run and Enter keeps it;
- validation success prints the `Connection OK` line and saves;
- validation failure prints the warning and still saves;
- `-c` selects and isolates the target profile.

## Docs

Add `config init` to the README command list. The drift-check test
(`tests/readme_check.py`) requires every README command to exist in the CLI, so
the README and the new command must land together.
