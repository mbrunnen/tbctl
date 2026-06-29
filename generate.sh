#!/usr/bin/env bash
# Regenerate the tb_client client from the ThingsBoard OpenAPI spec.
#
# The whole generator project is built into generated/ (gitignored);
# generated/tb_client is the importable package. The generator's package
# __init__.py files eagerly import the entire 762-model graph at import time,
# which hits a circular import, so they are replaced in place with import-safe
# versions: empty package inits plus a lazy __getattr__ loader for models.
set -euo pipefail

cd "$(dirname "$0")"

spec="openapi-4.3.0.1PE.json"
out="generated"
pkg="$out/tb_client"

openapi-generator-cli generate \
	-i "$spec" \
	-g python \
	--package-name tb_client \
	--skip-validate-spec \
	-o "$out"

printf '# generated client\n' >"$pkg/__init__.py"
printf '# generated\n' >"$pkg/api/__init__.py"
cat >"$pkg/models/__init__.py" <<'PY'
import importlib
import re


def _to_module(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def __getattr__(name: str):
    try:
        mod = importlib.import_module(f"tb_client.models.{_to_module(name)}")
        cls = getattr(mod, name)
        globals()[name] = cls
        return cls
    except (ImportError, AttributeError):
        raise AttributeError(f"module 'tb_client.models' has no attribute {name!r}")
PY

echo "Regenerated $pkg from $spec."
