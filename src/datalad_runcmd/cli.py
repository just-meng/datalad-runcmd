"""Command-line entry point for runcmd."""

from __future__ import annotations

import re
import sys
import argparse
from pathlib import Path

from .config import load_config
from .extract import extract_datalad_cmds, find_script, find_script_candidates, pick_cmd_for_cwd
from .resolve import ResolutionError, resolve_placeholder


_DATALAD_PLACEHOLDERS = frozenset({"inputs", "outputs"})


def _find_placeholders(cmd: str) -> list[str]:
    """Return placeholder names in order of first appearance in *cmd*.

    Placeholders look like ``{name}``.  Duplicates are kept only once,
    preserving first-occurrence order.  DataLad's own ``{inputs}`` and
    ``{outputs}`` tokens are excluded — they are resolved by ``datalad run``
    itself.
    """
    seen: set[str] = set()
    result: list[str] = []
    for m in re.finditer(r"\{([^}]+)\}", cmd):
        name = m.group(1)
        if name not in seen and name not in _DATALAD_PLACEHOLDERS:
            seen.add(name)
            result.append(name)
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="runcmd",
        description="Extract and resolve datalad run commands from script docstrings.",
    )
    parser.add_argument("script", help="Script filename (e.g. run_fissa.py)")
    parser.add_argument(
        "args",
        nargs="*",
        metavar="ARG",
        help="Positional arguments mapped to placeholders in occurrence order",
    )
    parsed = parser.parse_args(argv)

    cwd = Path.cwd()

    try:
        cfg = load_config(cwd)
    except FileNotFoundError as exc:
        sys.exit(f"Error: {exc}")

    script_path = find_script(parsed.script, cfg.script_dirs)
    if script_path is None:
        candidates = find_script_candidates(parsed.script, cfg.script_dirs)
        if candidates:
            suggestions = "\n".join(f"  {p.name}" for p in candidates)
            sys.exit(
                f"Error: '{parsed.script}' not found. Did you mean:\n{suggestions}"
            )
        sys.exit(
            f"Error: '{parsed.script}' not found in "
            f"{[str(d) for d in cfg.script_dirs]}"
        )

    cmds = extract_datalad_cmds(script_path)
    if not cmds:
        sys.exit(f"Error: no 'datalad run' command found in {script_path.name}")

    cmd = pick_cmd_for_cwd(cmds, cwd)
    placeholders = _find_placeholders(cmd)

    if len(parsed.args) < len(placeholders):
        sys.exit(
            f"Error: this script requires {len(placeholders)} argument(s) "
            f"({', '.join(placeholders)}), got {len(parsed.args)}"
        )

    for name, arg in zip(placeholders, parsed.args):
        spec = cfg.placeholders.get(name)
        if spec is None:
            # No config for this placeholder — substitute raw value
            cmd = cmd.replace(f"{{{name}}}", arg)
        else:
            try:
                resolved = resolve_placeholder(arg, spec, cfg.root)
            except ResolutionError as exc:
                sys.exit(f"Error resolving {{{name}}}: {exc}")
            print(f"  {{{name}}}: {arg!r} -> {resolved!r}", file=sys.stderr)
            cmd = cmd.replace(f"{{{name}}}", resolved)

    print(cmd)


if __name__ == "__main__":
    main()
