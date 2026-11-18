#!/usr/bin/env bash
# Run Flora with file-based memory injected as DATA (never as code).
# Usage: run_flora.sh [--no-memory] ["prompt"]     (prompt can also come from stdin; no prompt = interactive)
# Env:   FLORA_MODEL (default flora)  FLORA_MEMORY_DIR (default ./memory)  FLORA_MAX_MEMORY_CHARS (default 8000)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_NAME="${FLORA_MODEL:-flora}"
MEMORY_DIR="${FLORA_MEMORY_DIR:-$ROOT_DIR/memory}"
MAX_MEMORY_CHARS="${FLORA_MAX_MEMORY_CHARS:-8000}"
USE_MEMORY=1

usage() { sed -n '2,5p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --no-memory) USE_MEMORY=0; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) break ;;
  esac
done

command -v ollama >/dev/null 2>&1 || { echo "error: ollama is not installed or not on PATH" >&2; exit 127; }

PROMPT=""
if [ $# -gt 0 ]; then
  PROMPT="$*"
elif [ ! -t 0 ]; then
  PROMPT="$(cat)"
fi

CONTEXT=""
if [ "$USE_MEMORY" = 1 ] && [ -d "$MEMORY_DIR" ]; then
  for f in "$MEMORY_DIR"/*.md; do
    [ -f "$f" ] || continue
    CONTEXT+="[MEMORY FILE: $(basename "$f")]"$'\n'"$(cat "$f")"$'\n\n'
  done
  if [ "${#CONTEXT}" -gt "$MAX_MEMORY_CHARS" ]; then
    CONTEXT="${CONTEXT:0:$MAX_MEMORY_CHARS}"$'\n'"[MEMORY TRUNCATED]"$'\n\n'
  fi
fi

FULL="$CONTEXT"
[ -n "$CONTEXT" ] && FULL+="User input follows."$'\n'
FULL+="$PROMPT"

if [ -n "$PROMPT" ] || [ -n "$CONTEXT" ]; then
  exec ollama run "$MODEL_NAME" "$FULL"
fi
exec ollama run "$MODEL_NAME"
