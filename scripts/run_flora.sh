#!/bin/bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_NAME="flora"
MEMORY_DIR="$ROOT_DIR/memory"

CONTEXT=""

# Inject memory files as data only
if [ -d "$MEMORY_DIR" ]; then
  for f in "$MEMORY_DIR"/*.md; do
    [ -f "$f" ] || continue
    CONTEXT+="[MEMORY FILE: $(basename "$f")]\n"
    CONTEXT+="$(cat "$f")\n\n"
  done
fi

# If memory exists, pass it silently, otherwise start clean
if [ -n "$CONTEXT" ]; then
  ollama run "$MODEL_NAME" "$CONTEXT\nUser input will follow."
else
  ollama run "$MODEL_NAME"
fi