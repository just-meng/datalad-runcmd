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
	-o "01_suite2p/sub-240226O/exp-Saline" \
	"./code/src/process2p/run_suite2p.py {inputs} {outputs}"
```

`O` uniquely identified `sub-240226O`: the tool stripped the common prefix
`sub-` shared by all subjects, leaving unique parts like `240226O`, `240226I`,
etc., and matched `O` to `240226O`.  `Saline` matched `exp-Saline` the same
way.  The command template lives in the script's own docstring.

**Python 3.11+, stdlib only, no runtime dependencies.**

## How it works

1. You write a `datalad run` template in each script's docstring, using
   `{placeholder}` tokens for variable parts.
2. You describe how to resolve those placeholders in `.datalad/runcmd.toml`.
3. `runcmd <script> [args...]` extracts the template, resolves the
   placeholders from your short positional args, and prints the full command.

## Installation

```bash
uv tool install -e /path/to/datalad-runcmd   # local editable install as CLI tool
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
prefix = "sub-"                # optional: keep only candidates that start with this
scan_dirs = ["01_data"]        # fallback: scan for matching subdirectories

# ── Prefix-only (no lookup table) ─────────────────────────────────────────────
[runcmd.placeholders.exp-drug]
prefix = "exp-"                # prepend prefix when missing; arg is used as-is

# ── Explicit list ─────────────────────────────────────────────────────────────
[runcmd.placeholders.ses-id]
values = ["ses-pre-01", "ses-mid-01", "ses-post-01"]

# ── Unconfigured placeholders ─────────────────────────────────────────────────
# Placeholders with no entry in runcmd.toml are substituted verbatim.
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
4. **Unique top scorer wins.**  Ties (same score) list all tied candidates and
   ask you to be more specific.
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

## Usage

```
runcmd <script> [args...]
```

- **Positional args** map to `{placeholder}` tokens in order of appearance.
  No flags needed.
- **No placeholders?** `runcmd prepare_metadata.py` — no extra args.
- **Typo in script name?** Closest scripts with a `datalad run` block are
  suggested: `'proc' not found. Did you mean: process.py`
- **Multiple `datalad run` blocks?** The one whose `-i`/`-o` paths best
  match the current directory is selected automatically.
- **Works from subdirectories** — config is found by walking up from cwd.
- **Resolution info** printed to stderr shows what each arg matched to.

## Examples

All equivalent:
```console
$ runcmd run_suite2p O Saline                    # minimal
$ runcmd run_suite2p 240226O Saline              # more specific
$ runcmd run_suite2p.py sub-240226O exp-Saline   # fully qualified
```
