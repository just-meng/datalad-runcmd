# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`datalad-runcmd` extracts `datalad run` commands embedded in Python script docstrings and resolves `{placeholder}` tokens using configuration from `.datalad/runcmd.toml`. Python 3.11+, stdlib only, no runtime dependencies.

## Commands

```bash
pip install -e .              # Editable install
python3 -m pytest             # Run all tests
python3 -m pytest tests/test_resolve.py::test_prefix_adds_missing  # Single test
```

## Architecture

The pipeline is: **CLI → Config → Extract → Resolve**.

- **cli.py** — Entry point (`runcmd` command). Parses args, orchestrates the pipeline: load config, find script, extract commands, match positional args to placeholders, resolve, print.
- **config.py** — Loads `.datalad/runcmd.toml` by walking up from cwd. Defines `Config` and `PlaceholderSpec` dataclasses.
- **extract.py** — Finds scripts in configured `script_dirs`, extracts `datalad run` command blocks from docstrings (handles multi-line with backslash continuation), and picks the best command for cwd by scoring path matches.
- **resolve.py** — Resolves placeholders by type:
  - `prefix`: prepends a string if missing
  - `enum`: validates against allowed values
  - `lookup`: suffix-matches against a TSV file column, falls back to directory scan

## Configuration Format

Config lives at `<dataset-root>/.datalad/runcmd.toml`:

```toml
[runcmd]
script_dirs = ["path/to/script/dir"]

[runcmd.placeholders.sub-id]
type = "lookup"
file = "path/to/tsv"
column = 0
skip_header = true
scan_dirs = ["path/to/sub/dir"]     # fallback
prefix = "sub-"

[runcmd.placeholders.ses-id]
type = "prefix"
prefix = "ses-"
```

## Key Conventions

- Uses `tomllib` (Python 3.11 stdlib) for config parsing.
- Positional CLI args are matched to placeholders in order of first appearance in the command string.
- Unconfigured placeholders receive raw arg substitution without error.
- `ResolutionError` is the custom exception for failed placeholder resolution.
