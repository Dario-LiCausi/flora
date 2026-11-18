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
# 1. Install Ollama and pull a base model (a small one is enough)
ollama pull llama3.2:3b
# 2. Build the Flora model on that base
scripts/build_model.sh llama3.2:3b
# 3. Ask Flora something (memory from ./memory is added automatically)
scripts/run_flora.sh "Summarise these notes in three bullets: ..."
scripts/run_flora.sh --no-memory "Plain question with no memory"
echo "text from a pipe" | scripts/run_flora.sh --no-memory
```
Environment: `FLORA_MODEL` (model name), `FLORA_MEMORY_DIR`, `FLORA_MAX_MEMORY_CHARS` (default 8000).

## Layout
| Path | What |
|---|---|
| `models/Modelfile` | Fixed identity, behaviour rules, memory-write protocol, model settings |
| `prompts/` | The system prompt and the memory-loader text (readable copies) |
| `memory/` | Core identity, user preferences, project notes (Markdown, read-only at run time) |
| `scripts/run_flora.sh` | Wrapper: injects memory as labelled data, with a size cap |
| `scripts/build_model.sh` | Builds the Ollama model on a base model you choose |
| `tests/` | Shell tests using a stub `ollama` (no model needed). CI runs them with shellcheck |

## Limits (honest)
- Small local models can ignore rules. Flora's constraints are **prompt-level guidance, not a security boundary**.
  Do not give it access to anything it should not be able to affect, and always review its output.
- Quality depends on the base model; a 3B model is good for short, structured text jobs, not for hard reasoning.
- The wrapper limits memory size and never executes memory text, but it cannot stop a model from being wrong.

## How I use it
Flora handles small text jobs (short drafts, tidy-ups, extracting fields) next to larger agents in a home-lab setup
(see the sibling project [Mu-th-ur](https://github.com/Dario-LiCausi/Mu-th-ur)). Its output is always checked before use.

## Tests
```bash
bash tests/test_run_flora.sh      # 13 checks, stub ollama
shellcheck scripts/*.sh tests/*.sh
```

## Status and roadmap
Foundation, wrapper and tests are done. Next: a small set of evaluation prompts (does it stay concise, does it refuse to invent memory),
and an example memory-update review flow.

## Licence
MIT
