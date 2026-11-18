#!/usr/bin/env bash
# Build the "flora" model in Ollama from models/Modelfile, on a base model of your choice.
# Usage: build_model.sh [base-model]     (default: llama3.2:3b)   Env: FLORA_MODEL (name to create, default flora)
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="${1:-llama3.2:3b}"
NAME="${FLORA_MODEL:-flora}"
command -v ollama >/dev/null 2>&1 || { echo "error: ollama is not installed or not on PATH" >&2; exit 127; }
TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
sed "s#^FROM .*#FROM ${BASE}#" "$ROOT_DIR/models/Modelfile" > "$TMP"
ollama create "$NAME" -f "$TMP"
