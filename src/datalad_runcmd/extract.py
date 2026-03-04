"""Extract datalad run commands from script docstrings."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path


def find_script(name: str, script_dirs: list[Path]) -> Path | None:
    """Locate *name* (with or without .py suffix) in *script_dirs*."""
    if not name.endswith(".py"):
        name += ".py"
    for d in script_dirs:
        p = d / name
        if p.exists():
            return p
    return None


def find_script_candidates(name: str, script_dirs: list[Path]) -> list[Path]:
    """Return scripts with names similar to *name* that contain datalad run blocks.

    Used when :func:`find_script` returns ``None``.  Candidates are scripts
    whose stem contains the search term (case-insensitive) and that have at
    least one ``datalad run`` block in their docstring.  Results are sorted
    from most to least specific (score = ``len(name) / len(stem)``).
    """
    stem = name.removesuffix(".py").lower()
    scored: list[tuple[float, Path]] = []
    for d in script_dirs:
        if not d.is_dir():
            continue
        for py in sorted(d.glob("*.py")):
            py_stem = py.stem.lower()
            if stem in py_stem and extract_datalad_cmds(py):
                scored.append((len(stem) / len(py_stem), py))
    scored.sort(key=lambda t: -t[0])
    return [p for _, p in scored]


def _extract_one_cmd(content: str, start: int) -> str:
    """Extract a single datalad run block starting at *start*."""
    lines = content[start:].split("\n")
    cmd_lines: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        cmd_lines.append(line)
        if not stripped.endswith("\\"):
            # bare "datalad run" with args on the next line — keep going
            if stripped.strip() == "datalad run":
                continue
            break
    return textwrap.dedent("\n".join(cmd_lines)).strip()


def extract_datalad_cmds(script_path: Path) -> list[str]:
    """Extract all ``datalad run`` commands from *script_path*."""
    content = script_path.read_text()
    return [
        _extract_one_cmd(content, m.start())
        for m in re.finditer(
            r"^[ \t]*datalad run(?=[ \t\\]|$)", content, re.MULTILINE
        )
    ]


def pick_cmd_for_cwd(cmds: list[str], cwd: Path) -> str:
    """Pick the command whose concrete paths best match *cwd*."""
    if len(cmds) == 1:
        return cmds[0]

    best_cmd, best_score = cmds[0], -1
    for cmd in cmds:
        score = 0
        for m in re.finditer(r'-[io]\s+"([^"]+)"', cmd):
            p = m.group(1)
            if "{" in p or "*" in p or "?" in p:
                continue
            if (cwd / p).exists():
                score += 1
        if score > best_score:
            best_cmd, best_score = cmd, score
    return best_cmd
