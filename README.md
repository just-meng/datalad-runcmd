# datalad-runcmd

Stop copy-pasting `datalad run` commands. Embed them in your scripts, type
short aliases, and let `runcmd` do the rest.

```console
$ runcmd run_suite2p.py O Saline
  {sub-id}: 'O' -> 'sub-240226O'
  {exp-drug}: 'Saline' -> 'exp-Saline'
datalad run \
	-m "Run suite2p for sub-240226O, exp-Saline" \
	-i "inputs/L5b_2p/sub-240226O/exp-Saline/ses-pre" \
	-i "inputs/L5b_2p/sub-240226O/exp-Saline/ses-post" \
	-i "inputs/L5b_2p/subjects.tsv" \
	-i "inputs/L5b_2p/recordings.tsv" \
	-o "01_suite2p/sub-240226O/exp-Saline" \
	"./code/src/process2p/run_suite2p.py {inputs} {outputs}"
```

`O` uniquely matched `sub-240226O` via a lookup table. If multiple subject IDs
contained `O`, all would have been listed. `Saline` → `exp-Saline` via a
prefix rule.  The command template lives in the script's own docstring.

**Python 3.11+, stdlib only, no runtime dependencies.**

## How it works

1. You write a `datalad run` template in each script's docstring, using
   `{placeholder}` tokens for variable parts.
2. You describe how to resolve those placeholders in `.datalad/runcmd.toml`.
3. `runcmd <script> [args...]` extracts the template, resolves the
   placeholders from your short positional args, and prints the full command.

## Installation

```bash
uv tool install -e /path/to/datalad-runcmd   # local editable install as system CLI-tool
```

## Configuration

Create `.datalad/runcmd.toml` at the root of your DataLad dataset:

```toml
[runcmd]
script_dirs = ["path/to/script/dir"]

# ── Lookup from a file ────────────────────────────────────────────────────────
[runcmd.placeholders.sub-id]
file = "inputs/subjects.tsv"   # TSV, CSV, JSON, or plain text  (see below)
column = 0                     # 0-indexed column  (or use column_name = "participant_id")
skip_header = true
prefix = "sub-"                # keep only candidates that start with this prefix
scan_dirs = ["01_data"]        # fallback: scan for matching subdirectories

# ── Prefix-only (no lookup table) ─────────────────────────────────────────────
[runcmd.placeholders.exp-drug]
prefix = "exp-"                # prepend prefix when missing; arg is used as-is

# ── Explicit list ─────────────────────────────────────────────────────────────
[runcmd.placeholders.mode]
values = ["mode-fast", "mode-slow"]

# ── Raw / unconfigured ────────────────────────────────────────────────────────
# Placeholders with no entry in runcmd.toml are substituted verbatim — no lookup.
```

## Matching logic

All placeholder types use the same algorithm:

1. **Collect candidates** from `values`, `file`, and/or `scan_dirs` (any
   combination).
2. **Score each candidate** against your argument — score =
   `len(arg) / len(candidate)`, case-insensitive substring match; exact match
   = 1.0.
3. **Unique top scorer wins.**  If two candidates tie (same score), `runcmd`
   lists them and asks you to be more specific.
4. **No candidates configured** → raw substitution: return `prefix + arg`.

Examples with `prefix = "sub-"` and candidates `sub-001A  sub-002B  sub-003C`:

| Arg | Match | Score |
|-----|-------|-------|
| `A` | `sub-001A` | 1/8 |
| `001A` | `sub-001A` | 4/8 |
| `sub-001A` | `sub-001A` | exact (1.0) |
| `A` + `sub-999A` also present | ambiguous | tie at 1/8 |

## Lookup file formats

`runcmd` auto-detects the format from the file extension:

| Extension | Format | Notes |
|-----------|--------|-------|
| `.tsv` | Tab-separated | `column` or `column_name` selects the field |
| `.csv` | Comma-separated | same |
| `.json` | JSON | array → elements; object → keys |
| anything else | Plain text | one candidate per line |

Override auto-detection with `separator = "\t"` (or any delimiter).

## Usage

```
runcmd <script> [args...]
```

- **Positional args** map to `{placeholder}` tokens in the order they appear
  in the command. No flags needed.
- **No placeholders?** Just `runcmd prepare_metadata.py` — no extra args.
- **Typo in script name?** `runcmd` suggests the closest scripts that have a
  `datalad run` block: `Error: 'proc' not found. Did you mean: process.py`
- **Multiple `datalad run` blocks?** The one whose concrete `-i`/`-o` paths
  best match your current directory is selected automatically.
- **Works from subdirectories** — config is found by walking up from cwd.
- **Resolution info** is printed to stderr so you can see what matched.

## Example

All the following calls return the same `datalad run` command:
```console
$ runcmd run_suite2p O Saline                    # shortest
$ runcmd run_suite2p 240226O Saline              # more specific
$ runcmd run_suite2p.py sub-240226O exp-Saline   # fully qualified
```
