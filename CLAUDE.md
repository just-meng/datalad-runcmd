# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`datalad-runcmd` extracts `datalad run` commands embedded in Python script docstrings and resolves `{placeholder}` tokens using configuration from `.datalad/runcmd.toml`. Python 3.11+, stdlib only, no runtime dependencies.

## Repository Structure

```
datalad-runcmd/
├── pyproject.toml         # Build config, dependencies, entry points
├── README.md              # User-facing documentation
├── CLAUDE.md              # This file
└── src/
    └── datalad_runcmd/
        ├── __init__.py    # Package init + DataLad extension registration (command_suite)
        ├── __main__.py    # Entry point for `python -m datalad_runcmd`
        ├── cli.py         # Standalone CLI (argparse, orchestration)
        ├── config.py      # Configuration loading from .datalad/runcmd.toml
        ├── extract.py     # Script discovery and command extraction from docstrings
        ├── resolve.py     # Placeholder resolution engine
        └── dl_command.py  # DataLad Interface subclass for `datalad runcmd`
```

## Build and Run

```bash
# Install as a system tool (editable, isolated environment)
uv tool install -e .

# Run (three equivalent entry points)
runcmd run_suite2p.py O saline
datalad runcmd run_suite2p.py O saline   # requires datalad
python -m datalad_runcmd run_suite2p.py O saline

# Run tests
uv run --extra dev pytest
```

## Architecture

The pipeline is: **CLI → Config → Extract → Resolve**.

- **cli.py** — Entry point (`runcmd` command). Parses args, orchestrates the pipeline: load config, find script, extract commands, match positional args to placeholders, resolve, print. Falls back to fuzzy script suggestions (`find_script_candidates`) when exact match fails.
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

# Explicit list
[runcmd.placeholders.exp-drug]
values = ["exp-Ketamine", "exp-LSD", "exp-Saline", "exp-Saline2", "exp-Lisuride"]

# Prefix-only (no lookup table) — prepend prefix when missing; arg is used as-is
[runcmd.placeholders.ses-id]
prefix = "ses-"                # e.g. pre -> ses-pre, post -> ses-post
```

### DataLad Extension Registration

- `__init__.py` exports `command_suite` tuple
- `dl_command.py` defines `RunCmd(Interface)` with `_params_` dict and `@build_doc`
- `pyproject.toml` registers under `[project.entry-points."datalad.extensions"]`
- `dl_command.py` gracefully degrades to a stub class when DataLad is not installed

## Key Conventions

- Uses `tomllib` (Python 3.11 stdlib) for config parsing.
- Positional CLI args are matched to placeholders in order of first appearance in the command string.
- Unconfigured placeholders receive raw arg substitution without error.
- `ResolutionError` is the custom exception for failed placeholder resolution.
- File formats: `.tsv` (tab), `.csv` (comma), `.json` (array→elements / object→keys), other (plain text one per line). Override with `separator = "..."`.
- Common affix detection is case-insensitive; original candidate casing is preserved in output.
