# Flora: a small, controlled local LLM setup

[![tests](https://github.com/Dario-LiCausi/flora/actions/workflows/test.yml/badge.svg)](https://github.com/Dario-LiCausi/flora/actions/workflows/test.yml)

Flora is a local language model (run with [Ollama](https://ollama.com)) that is set up for **controlled use, not automation**.
It has a fixed identity, reads its memory from plain files, and never acts on its own.

## Design ideas
- **No autonomous actions.** Flora only answers. It does not run tools, edit files or change state.
- **Fixed identity.** Name and role live in the model file (`models/Modelfile`), not in memory.
- **External, file-based memory.** Memory is Markdown in `memory/`. It is read-only at run time and treated as *data*, never as instructions to execute.
- **Unknown stays unknown.** If something is not in memory, the model must say it does not know.
- **Propose, then approve.** Flora can draft a memory update when asked ("Propose memory update"), but a human decides. It never assumes approval.
- **Everything is inspectable.** Prompts, memory and the wrapper script are short plain-text files.

## Quick start
```bash
ollama pull llama3.2:3b                  # any small base model works
scripts/build_model.sh llama3.2:3b       # builds the "flora" model (fixed identity + rules)
bin/flora ask "Who are you?"             # memory from ./memory is added as labelled data
```
Python 3.9+ standard library only. No packages to install.

## Commands
| Command | What it does |
|---|---|
| `flora ask [--no-memory] "text"` | One question. Prompt can also come from a pipe. |
| `flora task summarise\|tidy\|ste\|extract\|copy "text"` | A small text job with a fixed prompt **and an output check**. Exit code 3 if the output fails its check. `extract` needs `--fields a,b,c` and must return exactly those JSON keys. `copy` writes 3 to 8 short options for a brief; with `--style-file examples.txt` it imitates the style of your examples and **fails the check if it copies 6 or more words in a row**. |
| `flora memory show\|list` | Show memory (capped) or the pending proposals. |
| `flora memory propose <target> "fact"` | Queue a memory change. **Nothing is written yet.** |
| `flora memory draft "what happened"` | Ask the model to draft one entry. It is saved as *pending*; the model never approves its own draft. |
| `flora memory approve <id> --yes` / `reject <id>` | The only way memory changes. Appends one line and writes an audit entry (the log records what happened, never the text). |
| `flora eval` | Runs `evals/cases.json` against the live model (concise output, ignores instructions hidden in the text, valid JSON, keeps unknown things unknown). |

Examples:
```bash
cat notes.txt | bin/flora task summarise            # at most 3 bullets, at most 80 words
bin/flora task ste "Prior to commencement of the procedure, ensure that the power is disconnected."
bin/flora task extract --fields name,date,amount "Invoice from Acme Ltd dated 3 March 2026 for 120 pounds."
bin/flora memory propose preferences "Prefers short answers" && bin/flora memory list
```
Environment: `FLORA_MODEL`, `FLORA_MEMORY_DIR`, `FLORA_HOST` (must be local; remote needs `FLORA_ALLOW_REMOTE=1`), `FLORA_MAX_MEMORY_CHARS`, `FLORA_TIMEOUT`.
The older shell wrapper `scripts/run_flora.sh` still works for interactive use.

## Layout
| Path | What |
|---|---|
| `models/Modelfile` | Fixed identity, behaviour rules, memory-write protocol, model settings |
| `prompts/` | The system prompt and the memory-loader text (readable copies) |
| `memory/` | Core identity, user preferences, project notes (Markdown, read-only at run time) |
| `flora/` | The Python package: `client` (local Ollama call), `memory` (load, propose, approve), `tasks` (jobs + output checks), `cli` |
| `evals/cases.json` | Evaluation cases for `flora eval` |
| `scripts/run_flora.sh` | Shell wrapper: injects memory as labelled data, with a size cap |
| `scripts/build_model.sh` | Builds the Ollama model on a base model you choose |
| `tests/` | Shell tests using a stub `ollama` (no model needed). CI runs them with shellcheck |

## Hardening (from an independent review)
No proxy and no redirects when talking to the model; a total time limit per request; memory and proposal files are read with size limits, never through symlinks or pipes; approval is atomic and writes exactly the text you were shown, once; proposal records are validated, not trusted; input text cannot close its own data block; bad settings and bad files give a clean error (exit code 2), never a crash.

## Limits (honest)
- Small local models can ignore rules. Flora's constraints are **prompt-level guidance, not a security boundary**.
  Do not give it access to anything it should not be able to affect, and always review its output.
- Quality depends on the base model; a 3B model is good for short, structured text jobs, not for hard reasoning.
- The wrapper limits memory size and never executes memory text, but it cannot stop a model from being wrong.
- A task check proves the *format* of an answer (for example, at most 3 bullets). It cannot prove the answer is true or that the model resisted a hidden instruction in the text; that is what `flora eval` samples.

## How I use it
Flora handles small text jobs (short drafts, tidy-ups, extracting fields) next to larger agents in a home-lab setup
(see the sibling project [Mu-th-ur](https://github.com/Dario-LiCausi/Mu-th-ur)). Its output is always checked before use.

## Tests
```bash
python3 -m unittest discover -s tests   # 44 tests; a stub server plays Ollama, no model needed
bash tests/test_run_flora.sh            # shell wrapper tests
bin/flora eval                          # live check against your model (needs Ollama)
```
Live result on 2026-11-18 with `llama3.2:3b`: 6 of 6 evaluation cases passed (results vary by model and run).

## Status and roadmap
v0.2: command line, five checked text jobs (including copywriting with a no-copying check), approval-based memory, audit log, evaluation cases, CI.
Next: more evaluation cases (long inputs, other languages), a small review screen for pending memory proposals,
and fine-tuning experiments on a small base model.

## Licence
MIT
