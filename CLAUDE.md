# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`datalad-runcmd` extracts `datalad run` commands embedded in Python script docstrings and resolves `{placeholder}` tokens using configuration from `.datalad/runcmd.toml`. Python 3.11+, stdlib only, no runtime dependencies.

## Commands

```bash
source .venv/bin/activate     # activate dev venv
python3 -m pytest             # run all tests
python3 -m pytest tests/test_resolve.py::test_raw_adds_prefix  # single test
```

### First-time dev setup (if .venv doesn't exist)
```bash
UV_CACHE_DIR=/tmp/uv-cache uv venv .venv
UV_CACHE_DIR=/tmp/uv-cache uv pip install --python .venv/bin/python -e ".[dev]"
```

## Architecture

The pipeline is: **CLI → Config → Extract → Resolve**.

- **cli.py** — Entry point (`runcmd` command). Parses args, orchestrates the pipeline: load config, find script, extract commands, match positional args to placeholders, resolve, print. Prints resolution info (`{name}: arg -> resolved`) to stderr. Falls back to fuzzy script suggestions (`find_script_candidates`) when exact match fails.
- **config.py** — Loads `.datalad/runcmd.toml` by walking up from cwd. Defines `Config` and `PlaceholderSpec` dataclasses. No `type` field — behaviour is inferred from which sources are configured.
- **extract.py** — Finds scripts in configured `script_dirs` (exact), or suggests fuzzy candidates via `find_script_candidates()`. Extracts `datalad run` command blocks from docstrings (handles multi-line with backslash continuation). Picks the best command for cwd by scoring path matches.
- **resolve.py** — Single unified resolution algorithm:
  1. Collect candidates from `values`, `file`, and/or `scan_dirs`.
  2. If no sources configured → raw substitution (optionally prepend `prefix`).
  3. Filter by `prefix` if set.
  4. Auto-detect common prefix/suffix of all candidates; trim to nearest separator (`-`, `_`, `.`) → **unique parts**.
  5. Score: exact full-string match = 1.0; exact unique-part match = 1.0; substring in unique part = `len(arg)/len(unique_part)`. Case-insensitive.
  6. Unique top scorer wins; tied matches list all options.

## Configuration Format

Config lives at `<dataset-root>/.datalad/runcmd.toml`:

```toml
[runcmd]
script_dirs = ["path/to/script/dir"]

# Lookup from file (TSV/CSV/JSON/plain text — auto-detected by extension)
[runcmd.placeholders.sub-id]
file = "path/to/tsv"
column = 0              # or column_name = "participant_id"
skip_header = true
prefix = "sub-"         # optional: filter to candidates starting with prefix
scan_dirs = ["path/to/sub/dir"]     # fallback: scan for matching subdirs

# Prefix-only (no lookup table) — prepend prefix when missing
[runcmd.placeholders.ses-id]
prefix = "ses-"

# Explicit list
[runcmd.placeholders.mode]
values = ["mode-fast", "mode-slow"]
```

## Key Conventions

- Uses `tomllib` (Python 3.11 stdlib) for config parsing.
- Positional CLI args are matched to placeholders in order of first appearance in the command string.
- Unconfigured placeholders receive raw arg substitution without error.
- `ResolutionError` is the custom exception for failed placeholder resolution.
- File formats: `.tsv` (tab), `.csv` (comma), `.json` (array→elements / object→keys), other (plain text one per line). Override with `separator = "..."`.
- Common affix detection is case-insensitive; original candidate casing is preserved in output.
