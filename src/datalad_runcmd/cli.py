"""Command-line entry point for runcmd."""

from __future__ import annotations

import os
import re
import sys
import argparse
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, load_config
from .extract import (
    CommandWarning,
    ExtractedCommand,
    extract_datalad_cmds,
    find_script,
    find_script_candidates,
    score_commands,
)
from .resolve import ResolutionError, resolve_placeholder


_DATALAD_PLACEHOLDERS = frozenset({"inputs", "outputs"})


@dataclass
class ResolvedResult:
    """Result of resolving a script's datalad run command(s)."""

    command: str
    all_commands: list[ExtractedCommand]
    warnings: list[CommandWarning] = field(default_factory=list)


def _all_script_placeholders(script_dirs: list[Path]) -> set[str]:
    """Collect every placeholder name used across all scripts in *script_dirs*."""
    names: set[str] = set()
    for d in script_dirs:
        if not d.is_dir():
            continue
        for py in d.glob("*.py"):
            for ecmd in extract_datalad_cmds(py):
                names.update(_find_placeholders(ecmd.validated))
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


def resolve_command(
    script: str, args: list[str], cwd: Path | None = None
) -> ResolvedResult:
    """Find a script, extract its datalad run command(s), and resolve placeholders.

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
    ResolvedResult
        Contains the resolved best-match command, all extracted commands
        (scored), and aggregated warnings.

    Raises
    ------
    ValueError
        If the script is not found, has no ``datalad run`` block, or
        the wrong number of arguments is provided.
    ResolutionError
        If placeholder resolution fails (ambiguous match, no match, etc.).
    """
    if cwd is None:
        cwd = Path.cwd()

    try:
        cfg = load_config(cwd)
    except FileNotFoundError:
        print(
            "Warning: no .datalad/runcmd.toml found — "
            "using raw placeholder substitution",
            file=sys.stderr,
        )
        cfg = Config(root=cwd, script_dirs=[cwd], placeholders={})

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

    ecmds = extract_datalad_cmds(script_path)
    if not ecmds:
        raise ValueError(f"no 'datalad run' command found in {script_path.name}")

    score_commands(ecmds, cwd)

    # Collect all warnings from all commands
    all_warnings: list[CommandWarning] = []
    for ecmd in ecmds:
        all_warnings.extend(ecmd.warnings)

    # Resolve placeholders on the best-match command
    best = ecmds[0]
    cmd = best.validated
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

    # Also resolve the other commands for display purposes
    for ecmd in ecmds:
        if ecmd is best:
            continue
        resolved_cmd = ecmd.validated
        ecmd_placeholders = _find_placeholders(resolved_cmd)
        for name, arg in zip(ecmd_placeholders, args):
            spec = cfg.placeholders.get(name)
            if spec is None:
                resolved_cmd = resolved_cmd.replace(f"{{{name}}}", arg)
            else:
                try:
                    resolved_val = resolve_placeholder(arg, spec, cfg.root)
                    resolved_cmd = resolved_cmd.replace(f"{{{name}}}", resolved_val)
                except ResolutionError:
                    pass  # leave unresolved for display
        ecmd.validated = resolved_cmd

    best.validated = cmd

    # Lint: warn about config keys that no script uses
    used = _all_script_placeholders(cfg.script_dirs)
    orphaned = sorted(set(cfg.placeholders) - used)
    for key in orphaned:
        print(f"Warning: config defines {{'{key}'}} but no script uses it", file=sys.stderr)

    return ResolvedResult(
        command=cmd,
        all_commands=ecmds,
        warnings=all_warnings,
    )


def _use_color(stream=None) -> bool:
    """Return True when ANSI color codes should be used."""
    if stream is None:
        stream = sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


# ANSI escape helpers — return empty strings when color is disabled.
def _ansi(code: str, color: bool) -> str:
    return f"\033[{code}m" if color else ""


def _format_warnings(warnings: list[CommandWarning]) -> str:
    """Format warnings for stderr output."""
    color = _use_color(sys.stderr)
    yellow = _ansi("33", color)
    reset = _ansi("0", color)
    lines: list[str] = []
    for w in warnings:
        lines.append(f"{yellow}Warning:{reset} {w.message}")
    return "\n".join(lines)


def _format_multi_command(ecmds: list[ExtractedCommand]) -> str:
    """Format multiple commands for display on stdout."""
    color = _use_color(sys.stdout)
    green = _ansi("32", color)
    dim = _ansi("2", color)
    reset = _ansi("0", color)

    parts: list[str] = []
    for i, ecmd in enumerate(ecmds, 1):
        label = ecmd.label or f"Command {i}"
        marker = f" {green}\u2190 best match{reset}" if ecmd.is_best else ""
        header = f"{dim}\u2500\u2500 [{i}] {label}{reset}{marker} "
        header += f"{dim}{'─' * max(1, 60 - len(label) - 10)}{reset}"
        parts.append(header)
        parts.append(ecmd.validated)
        parts.append("")
    return "\n".join(parts)


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
        result = resolve_command(parsed.script, parsed.args)
    except (ValueError, ResolutionError) as exc:
        sys.exit(f"Error: {exc}")

    # Print warnings to stderr
    if result.warnings:
        print(_format_warnings(result.warnings), file=sys.stderr)

    # Print command(s) to stdout
    if len(result.all_commands) > 1:
        print(_format_multi_command(result.all_commands))
    else:
        print(result.command)


if __name__ == "__main__":
    main()
