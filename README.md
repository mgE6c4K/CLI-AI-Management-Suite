# CLI AI Management Suite

`om` manages local AI from the terminal: Ollama models, Claude Code running on them, chats with local models,
and backups of both Claude's and Ollama's local data. Python standard library only.

## Requirements

- macOS or Linux, Python 3.9+
- [Ollama](https://ollama.com)
- Optional: Claude Code (`claude`) for `om claude`
- Optional: the `claude-backup` add-on (a submodule; needs a C compiler and zlib) for claude-local backups

## Install

```bash
git clone --recurse-submodules <repo-url> CLI-AI-Management-Suite
cd CLI-AI-Management-Suite
make install        # links `om` into ~/.local/bin and builds the claude-backup add-on if it is checked out
```

or, without the add-on, `pipx install .` (install claude-backup separately with `make -C claude-backup install`).

For nvim's codecompanion, add this to your shell rc so new shells get `OLLAMA_HOST` and `OLLAMA_MODEL`:

```bash
eval "$(om env)"
```

## Use

`om` opens the TUI. Pages come in three groups; press a group number, then a page number
(`1 2` is the market). The group blinks while om waits for the second number, and `0` goes back.

| Group | Pages |
|---|---|
| 1 ollama | llms, market, settings (server env vars) |
| 2 local | configs, files, system, chats, backups |
| 3 om | settings (screensaver, progress style, walker, accent colour) |

`h` shows every key on the current page.

```
om ls | pull | rm | stop | up        manage models
om base | use <model>                cc-longwork, the model om claude runs, and its base
om nvim [model]                      the model codecompanion uses
om env                               shell exports for nvim
om claude [-m model] [dir] [args]    Claude Code on local Ollama
om backup                            back up claude-local and ollama-local
om apply | upgrade                   restart or upgrade the Ollama service (brew on macOS)
```

## Where things live

- `~/.config/om`: your settings, model library, nvim model and the cc-longwork Modelfile
- `~/.local/state/om`: ollama-local chats and background download progress
- Backups: `<backup folder>/ClaudeBackups` and `OllamaBackups`, with the folder set on the configs page (default `~/Documents`)

## Test

```bash
make test
```
