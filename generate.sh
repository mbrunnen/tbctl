#!/usr/bin/env bash
set -euo pipefail

openapi-generator generate \
  -i openapi.json \
  -g python \
  -o tb_client \
  --package-name tb_client \
  --additional-properties=generateSourceCodeOnly=true
