# datalad-runcmd

Stop copy-pasting `datalad run` commands. Embed them in your scripts, type
short aliases, and let `runcmd` do the rest.

```console
$ runcmd run_suite2p.py O Saline
datalad run \
	-m "Run suite2p for sub-240226O, exp-Saline" \
	-i "inputs/L5b_2p/sub-240226O/exp-Saline/ses-pre" \
	-i "inputs/L5b_2p/sub-240226O/exp-Saline/ses-post" \
	-i "inputs/L5b_2p/subjects.tsv" \
	-i "inputs/L5b_2p/recordings.tsv" \
	-o "01_suite2p/sub-240226O/exp-Saline" \
	"./code/src/process2p/run_suite2p.py {inputs} {outputs}"
```

`O` auto-matched to `sub-240226O` via a lookup table, since it is uniquely assigned to one subject. If multiple subject 
IDs contained `O`, all would have been listed. Likewise `Saline` matched to `exp-Saline`. The command template lives in the 
script's own docstring.

**Python 3.11+, stdlib only, no runtime dependencies.**

## How it works

1. You write a `datalad run` template in each script's docstring, using
   `{placeholder}` tokens for variable parts.
2. You describe how to resolve those placeholders in `.datalad/runcmd.toml`.
3. `runcmd <script> [args...]` extracts the template, resolves the
   placeholders from your short positional args, and prints the full command.

## Installation

```bash
uv tool -e /path/to/datalad-runcmd   # local editable install as system CLI-tool
```

## Configuration

Create `.datalad/runcmd.toml` at the root of your DataLad dataset:

```toml
[runcmd]
script_dirs = ["path/to/script/dir"]    # path to dirs containing your script

# add a rule for each placeholder variable
[runcmd.placeholders.sub-id]            # placeholder variable, e.g. 'sub-id', 'ses-id' 
type = "lookup"                         # lookup table containing all sub-ids
file = "path/to/tsv"                    
column = 0                              # 0-indexed, column to lookup
skip_header = true
scan_dirs = ["path/to/sub/dir"]         # fallback: scan for matching dirs
```

### Placeholder types

| Type | Resolves | Example |
|------|----------|---------|
| **lookup** | Suffix-match against a TSV column or directory names | `O` -> `sub-240226O` |
| **prefix** | Prepend a prefix if missing | `Saline` -> `exp-Saline` |
| **enum** | Validate against a fixed list of allowed values | `fast` (must be in `values`) |

`lookup` tries the TSV file first, falls back to scanning directories under
`scan_dirs`, and errors on ambiguous matches.

Add your own type and rule in ...?

## Usage

```
runcmd <script> [args...]
```

- **Positional args** map to `{placeholder}` tokens in the order they appear
  in the command. No flags needed.
- **No placeholders?** Just `runcmd prepare_metadata.py` — no extra args.
- **Multiple `datalad run` blocks?** The one whose concrete `-i`/`-o` paths
  best match your current directory is selected automatically.
- **Works from subdirectories** — config is found by walking up from cwd.

## Example

All the following calls return the same `datalad run` command:
```console
$ runcmd run_suite2p O Saline                    # shortest command                                                                                             
$ runcmd run_suite2p 240226O Saline              # arbitrarily specific command                                                                             
$ runcmd run_suite2p.py sub-240226I exp-Saline   # full command                                                                       
```
