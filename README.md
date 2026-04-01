# datalad-runcmd

Stop copy-pasting `datalad run` commands. Embed them in your scripts, type
short aliases, and let `runcmd` do the rest.

```console
$ runcmd run_suite2p.py O saline
datalad run \
	-m "Run suite2p for sub-240226O, exp-Saline" \
	-i "inputs/L5b_2p/sub-240226O/exp-Saline/ses-pre" \
	-i "inputs/L5b_2p/sub-240226O/exp-Saline/ses-post" \
	-i "inputs/L5b_2p/subjects.tsv" \
	-o "01_suite2p/sub-240226O/exp-Saline" \
	"./code/src/process2p/run_suite2p.py {inputs} {outputs}"
```

The tool **looks up** which `sub-id` matches `O` and which `exp-id` matches `saline`,
and **replaces** all occurrences in the command template with the full IDs: `sub-240226O`,
`exp-Saline`. The command template simply lives inside the docstring of the script `run_suite2p.py`.

**Python 3.11+, stdlib only, no runtime dependencies.**

## How it works

1. You write a `datalad run` template in each script's docstring, using
   `{placeholder}` tokens for variable parts.
2. Optionally, describe how to resolve those placeholders in
   `.datalad/runcmd.toml` (fuzzy matching, lookup tables, prefix rules).
   Without a config file, placeholders are substituted verbatim.
3. `runcmd <script> [args...]` extracts the template, resolves the
   placeholders from your short positional args, and prints the full command.

## Installation

As a DataLad extension from GitHub:

```bash
uv tool install datalad \
  --with datalad-next \
  --with datalad-container \
  --with datalad-runcmd@git+https://github.com/just-meng/datalad-runcmd.git
```

For local development (editable — code changes take effect immediately,
no reinstall needed):

```bash
# Standalone CLI
uv tool install -e /path/to/datalad-runcmd

# DataLad extension (editable)
uv tool install datalad \
  --with-editable /path/to/datalad-runcmd \
  --force
```

> **Note:** `--with-editable` requires a local path — it cannot be combined
> with a git URL. Use `--with ...@git+https://...` for non-editable remote
> installs, or clone the repo locally first.

> **Note:** There is an unrelated `runcmd` package on PyPI. Always install
> from the local path or the GitHub URL — never `uv tool install runcmd`.

For running tests:

```bash
cd datalad-runcmd
uv run --extra dev pytest
```

## Configuration

Configuration is **optional**. Without a `.datalad/runcmd.toml`, `runcmd`
looks for scripts in the current directory and substitutes placeholders
verbatim (a warning is printed to stderr). This is useful for simple
scripts that don't need fuzzy matching or lookup tables.

For full placeholder resolution, create `.datalad/runcmd.toml` at the root
of your DataLad dataset:

```toml
[runcmd]
script_dirs = ["path/to/script/dir"]

# ── Lookup from a file ────────────────────────────────────────────────────────
[runcmd.placeholders.sub-id]
file = "inputs/subjects.tsv"   # TSV, CSV, JSON, or plain text  (see below)
column = 0                     # 0-indexed column  (or use column_name = "participant_id")
skip_header = true
prefix = "sub-"                # optional: keep only candidates that start with this
scan_dirs = ["01_data"]        # fallback: scan for matching subdirectories

# ── Explicit list ─────────────────────────────────────────────────────────────
[runcmd.placeholders.exp-id]   # match to a list of values instead of a lookup table
values = ["exp-Ketamine", "exp-LSD", "exp-Saline", "exp-Saline2", "exp-Lisuride"]

# ── Prefix-only (no lookup table) ─────────────────────────────────────────────
[runcmd.placeholders.ses-id]
prefix = "ses-"                # prepend prefix when missing, no matching; e.g. pre -> ses-pre

# ── Unconfigured placeholders ─────────────────────────────────────────────────
# Placeholders with no entry in runcmd.toml are substituted verbatim.
```

## Usage

### Standalone CLI

```
runcmd <script> [args...]
```

- **Positional args** map to `{placeholder}` tokens in order of appearance.
  No flags needed.
- **No placeholders?** `runcmd prepare_metadata.py` — no extra args.
- **Typo in script name?** Closest scripts with a `datalad run` block are
  suggested: `'proc' not found. Did you mean: process.py`
- **Multiple `datalad run` blocks?** All are shown with labeled headers
  (extracted from the text preceding each block in the docstring) and a
  "best match" indicator based on which `-i`/`-o` paths exist in the cwd.
- **Works from subdirectories** — config is found by walking up from cwd.
- **No config file?** Scripts are found in cwd and placeholders are
  substituted verbatim. A warning is printed to stderr.

### DataLad Command

If DataLad is installed, the tool registers as a DataLad extension:

```bash
datalad runcmd run_suite2p.py O saline
datalad runcmd run_fissa.py ket pre
```

### As a Python Module

```bash
python -m datalad_runcmd run_suite2p.py O saline
```

## Matching logic

All placeholder types use the same algorithm:

1. **Collect candidates** from `values`, `file`, and/or `scan_dirs`.
2. **Strip the common affix** shared by all candidates, trimmed to the
   nearest separator (`-`, `_`, `.`), to isolate each candidate's *unique
   part*:

   | Candidates | Common affix stripped | Unique parts |
   |---|---|---|
   | `sub-001A  sub-002B  sub-003C` | prefix `sub-` | `001A  002B  003C` |
   | `ses-pre-01  ses-mid-01  ses-post-01` | prefix `ses-`, suffix `-01` | `pre  mid  post` |
   | `exp-Saline  exp-LSD` | prefix `exp-` | `Saline  LSD` |

3. **Score** each candidate against your argument — case-insensitive
   substring match in the unique part; score = `len(arg) / len(unique_part)`;
   full-string exact match = 1.0.
4. **Unique top scorer wins.**  Ties print a one-line error listing the
   candidates: `Ambiguous '00': sub-001A, sub-002A`.
5. **No candidates configured** → raw substitution: return `prefix + arg`.

Examples with unique parts `001A  002B  003C`:

| Arg | Matches | Result |
|-----|---------|--------|
| `A` | `001A` only | `sub-001A` |
| `001A` | exact on `001A` | `sub-001A` |
| `sub-001A` | exact on full string | `sub-001A` |
| `00` | `001A` and `002A` (if present) equally | ambiguous error |

## Lookup file formats

Auto-detected by extension:

| Extension | Format | Notes |
|-----------|--------|-------|
| `.tsv` | Tab-separated | `column` or `column_name` selects the field |
| `.csv` | Comma-separated | same |
| `.json` | JSON | array → elements; object → keys |
| anything else | Plain text | one candidate per line |

Override auto-detection with `separator = "\t"` (or any delimiter).

## Examples

All equivalent:
```console
$ runcmd run_suite2p O Sal                       # minimal
$ runcmd run_suite2p 240226O Saline              # more specific
$ runcmd run_suite2p.py sub-240226O exp-Saline   # fully qualified
```

## License

MIT
