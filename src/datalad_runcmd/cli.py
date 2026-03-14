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


def _all_script_placeholders(script_dirs: list[Path]) -> set[str]:
    """Collect every placeholder name used across all scripts in *script_dirs*."""
    names: set[str] = set()
    for d in script_dirs:
        if not d.is_dir():
            continue
        for py in d.glob("*.py"):
            for cmd in extract_datalad_cmds(py):
                names.update(_find_placeholders(cmd))
    return names


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


def resolve_command(script: str, args: list[str], cwd: Path | None = None) -> str:
    """Find a script, extract its datalad run command, and resolve placeholders.

    Parameters
    ----------
    script : str
        Script filename (e.g. ``run_fissa.py``).
    args : list[str]
        Positional arguments mapped to placeholders in occurrence order.
    cwd : Path, optional
        Working directory for config lookup and command selection.
        Defaults to ``Path.cwd()``.

    Returns
    -------
    str
        The fully resolved ``datalad run`` command.

    Raises
    ------
    FileNotFoundError
        If ``.datalad/runcmd.toml`` is not found.
    ValueError
        If the script is not found, has no ``datalad run`` block, or
        the wrong number of arguments is provided.
    ResolutionError
        If placeholder resolution fails (ambiguous match, no match, etc.).
    """
    if cwd is None:
        cwd = Path.cwd()

    cfg = load_config(cwd)

    script_path = find_script(script, cfg.script_dirs)
    if script_path is None:
        candidates = find_script_candidates(script, cfg.script_dirs)
        if candidates:
            suggestions = "\n".join(f"  {p.name}" for p in candidates)
            raise ValueError(
                f"'{script}' not found. Did you mean:\n{suggestions}"
            )
        raise ValueError(
            f"'{script}' not found in "
            f"{[str(d) for d in cfg.script_dirs]}"
        )

    cmds = extract_datalad_cmds(script_path)
    if not cmds:
        raise ValueError(f"no 'datalad run' command found in {script_path.name}")

    cmd = pick_cmd_for_cwd(cmds, cwd)
    placeholders = _find_placeholders(cmd)

    if len(args) < len(placeholders):
        raise ValueError(
            f"this script requires {len(placeholders)} argument(s) "
            f"({', '.join(placeholders)}), got {len(args)}"
        )

    for name, arg in zip(placeholders, args):
        spec = cfg.placeholders.get(name)
        if spec is None:
            cmd = cmd.replace(f"{{{name}}}", arg)
        else:
            resolved = resolve_placeholder(arg, spec, cfg.root)
            cmd = cmd.replace(f"{{{name}}}", resolved)

    # Lint: warn about config keys that no script uses
    used = _all_script_placeholders(cfg.script_dirs)
    orphaned = sorted(set(cfg.placeholders) - used)
    for key in orphaned:
        print(f"Warning: config defines {{'{key}'}} but no script uses it", file=sys.stderr)

    return cmd


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

    try:
        cmd = resolve_command(parsed.script, parsed.args)
    except (FileNotFoundError, ValueError, ResolutionError) as exc:
        sys.exit(f"Error: {exc}")

    print(cmd)


if __name__ == "__main__":
    main()
