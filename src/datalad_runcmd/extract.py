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
