#!/usr/bin/env bash
# shellcheck disable=SC2016,SC2034  # check() strings are single-quoted on purpose (evaluated later); rc is read inside them
# Tests for scripts/run_flora.sh using a stub "ollama" (no model needed). Run: bash tests/test_run_flora.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../scripts/run_flora.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/mem"
cat > "$TMP/bin/ollama" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$STUB_OUT"
STUB
chmod +x "$TMP/bin/ollama"
printf 'Flora is local.\n' > "$TMP/mem/core.md"
printf 'UK English.\n' > "$TMP/mem/preferences.md"
export STUB_OUT="$TMP/out.txt" FLORA_MEMORY_DIR="$TMP/mem"
FAILS=0
ok()   { echo "ok   - $1"; }
fail() { echo "FAIL - $1"; FAILS=$((FAILS+1)); }
check() { if eval "$2"; then ok "$1"; else fail "$1"; fi; }

PATH="$TMP/bin:$PATH" "$SCRIPT" "hello there" >/dev/null 2>&1
check "model name is passed first"            'head -2 "$STUB_OUT" | grep -qx "run" && sed -n 2p "$STUB_OUT" | grep -qx "flora"'
check "memory files are injected with labels" 'grep -q "\[MEMORY FILE: core.md\]" "$STUB_OUT" && grep -q "\[MEMORY FILE: preferences.md\]" "$STUB_OUT"'
check "memory text is included"               'grep -q "Flora is local." "$STUB_OUT"'
check "user prompt comes after memory"        '[ "$(grep -n "User input follows" "$STUB_OUT" | cut -d: -f1)" -lt "$(grep -n "hello there" "$STUB_OUT" | cut -d: -f1)" ]'

PATH="$TMP/bin:$PATH" "$SCRIPT" --no-memory "just this" >/dev/null 2>&1
check "--no-memory sends no memory"           '! grep -q "MEMORY FILE" "$STUB_OUT" && grep -q "just this" "$STUB_OUT"'

echo "from stdin" | PATH="$TMP/bin:$PATH" "$SCRIPT" --no-memory >/dev/null 2>&1
check "prompt can come from stdin"            'grep -q "from stdin" "$STUB_OUT"'

FLORA_MODEL=other PATH="$TMP/bin:$PATH" "$SCRIPT" --no-memory "x" >/dev/null 2>&1
check "FLORA_MODEL overrides the model"       'sed -n 2p "$STUB_OUT" | grep -qx "other"'

head -c 20000 /dev/zero | tr '\0' 'a' > "$TMP/mem/big.md"
FLORA_MAX_MEMORY_CHARS=500 PATH="$TMP/bin:$PATH" "$SCRIPT" "q" >/dev/null 2>&1
check "oversized memory is truncated"         'grep -q "MEMORY TRUNCATED" "$STUB_OUT" && [ "$(wc -c < "$STUB_OUT")" -lt 1500 ]'
rm "$TMP/mem/big.md"

printf '$(touch %s/pwned)\n`touch %s/pwned2`\n' "$TMP" "$TMP" > "$TMP/mem/evil.md"
PATH="$TMP/bin:$PATH" "$SCRIPT" "q" >/dev/null 2>&1
check "memory text is data, never executed"   '[ ! -e "$TMP/pwned" ] && [ ! -e "$TMP/pwned2" ] && grep -qF "touch" "$STUB_OUT"'
rm "$TMP/mem/evil.md"

PATH="/usr/bin:/bin" "$SCRIPT" "x" >/dev/null 2>"$TMP/err.txt"; rc=$?
check "missing ollama gives a clear error"    '[ "$rc" = 127 ] && grep -q "ollama is not installed" "$TMP/err.txt"'

"$SCRIPT" --bogus >/dev/null 2>&1; rc=$?
check "unknown option is rejected"            '[ "$rc" = 2 ]'

cat > "$TMP/bin/ollama" <<'STUB2'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$STUB_OUT"
[ "$1" = create ] && cp "$4" "$STUB_OUT.modelfile"
STUB2
PATH="$TMP/bin:$PATH" "$HERE/../scripts/build_model.sh" mistral >/dev/null 2>&1
check "build_model.sh creates the model by name" 'sed -n 1,2p "$STUB_OUT" | tr "\n" " " | grep -q "create flora"'
check "build_model.sh swaps the base model"      'head -1 "$STUB_OUT.modelfile" | grep -qx "FROM mistral"'

if [ "$FAILS" = 0 ]; then echo "ALL PASSED"; else echo "$FAILS FAILED"; exit 1; fi
