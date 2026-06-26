#!/usr/bin/env bash
# Regenerate the tb_client package from openapi.json.
#
# The generated bulk (api/, models/, runtime helpers) is gitignored. A small
# hand-maintained customisation layer is committed and restored after each
# generation:
#   - api_client.py        strips RFC 6570 {?query} fragments from resource paths
#   - __init__.py          empty, to avoid eager imports
#   - api/__init__.py      empty, to avoid eager imports
#   - models/__init__.py   lazy __getattr__ loader, to break circular imports
set -euo pipefail

cd "$(dirname "$0")"

spec="openapi.json"
pkg="tb_client"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

openapi-generator-cli generate \
	-i "$spec" \
	-g python \
	--package-name "$pkg" \
	--skip-validate-spec \
	-o "$tmp"

rm -rf "$pkg/api" "$pkg/models"
cp -r "$tmp/$pkg/api" "$tmp/$pkg/models" "$pkg/"
cp "$tmp/$pkg/rest.py" "$tmp/$pkg/configuration.py" \
	"$tmp/$pkg/exceptions.py" "$tmp/$pkg/api_response.py" "$pkg/"

# Restore the committed customisation layer over the fresh generator output.
git checkout -- \
	"$pkg/__init__.py" \
	"$pkg/api/__init__.py" \
	"$pkg/models/__init__.py" \
	"$pkg/api_client.py"

uv run --with ruff ruff format "$pkg/" >/dev/null

echo "Regenerated $pkg from $spec."
