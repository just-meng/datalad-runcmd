"""Extract datalad run commands from script docstrings."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CommandWarning:
    """A fixable issue detected during command validation."""

    category: str  # "unquoted_glob", "double_backslash", "missing_executable", etc.
    message: str


@dataclass
class ExtractedCommand:
    """A datalad run command extracted from a docstring, with metadata."""

    raw: str
    label: str
    validated: str
    warnings: list[CommandWarning] = field(default_factory=list)
    score: float = 0.0
    is_best: bool = False


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


def _extract_label(content: str, cmd_start: int) -> str:
    """Extract the descriptive label preceding a ``datalad run`` block.

    Walks backward from *cmd_start* looking for the nearest non-blank line
    that is not part of a command block or a docstring delimiter.
    """
    before = content[:cmd_start]
    lines = before.rstrip().split("\n")
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # docstring delimiters
        if stripped in ('"""', "'''"):
            return ""
        if stripped.startswith('"""') or stripped.startswith("'''"):
            return ""
        # part of a previous datalad run command
        if stripped.endswith("\\"):
            return ""
        if stripped.startswith('"') or stripped.startswith("'"):
            return ""
        if stripped.startswith("-"):
            return ""
        if "datalad run" in stripped:
            return ""
        return stripped.rstrip(":")
    return ""


def _join_continuations(cmd: str) -> str:
    """Join backslash-continuation lines into a single line."""
    return re.sub(r"\\\n\s*", " ", cmd)


def _is_valid_command(raw: str) -> bool:
    """Check whether *raw* looks like a runnable ``datalad run`` command.

    Rejects false positives like ``datalad run (comment about something):``.
    A valid command must have recognised flags (``-m``, ``-i``, ``-o``) or
    end with an executable (a quoted or path-like final argument).
    """
    joined = _join_continuations(raw)
    rest = joined.strip()
    if not rest.startswith("datalad run"):
        return False
    rest = rest[len("datalad run") :].strip()
    if not rest:
        return False
    # Parenthetical comment — not a real command
    if rest.startswith("("):
        return False
    # Must contain recognised flags or a quoted executable
    has_flag = bool(
        re.search(
            r"-[miod]\b|--(?:input|output|message|dataset)\b", rest
        )
    )
    has_quoted = bool(re.search(r"""["'][^"']*["']\s*$""", rest.rstrip()))
    return has_flag or has_quoted


def validate_command(raw: str) -> tuple[str, list[CommandWarning]]:
    """Validate and auto-fix a ``datalad run`` command.

    Returns the (possibly fixed) command and a list of warnings.
    """
    warnings: list[CommandWarning] = []
    cmd = raw

    joined = _join_continuations(cmd)

    # 1. Check: ends with an executable command
    # After all flags and their values, there should be a final positional arg
    rest = joined.strip()
    if rest.startswith("datalad run"):
        rest = rest[len("datalad run") :].strip()
    # Remove all flag+value pairs: -m "...", -i "...", -o "...", --input "...", etc.
    stripped_rest = re.sub(
        r"""--?(?:message|input|output|dataset|[miod])\s+(?:"[^"]*"|'[^']*'|\S+)""",
        "",
        rest,
    ).strip()
    if not stripped_rest:
        warnings.append(
            CommandWarning(
                category="missing_executable",
                message="Command has no executable to run "
                "(the final positional argument is missing)",
            )
        )

    # 2. Check: double backslash line continuations (\\)
    # In raw file content, a proper continuation is \.
    # \\ in the extracted text means two backslash characters.
    double_bs = re.compile(r"\\\\[ \t]*$", re.MULTILINE)
    if double_bs.search(cmd):
        cmd = double_bs.sub(r"\\", cmd)
        warnings.append(
            CommandWarning(
                category="double_backslash",
                message="Double backslash (\\\\) in line continuation "
                "replaced with single (\\)",
            )
        )

    # 3. Check: unquoted glob patterns in -i/-o arguments
    unquoted_glob = re.compile(
        r"(-[io])\s+([^\s\"']+[*?][^\s\"']*)"
    )

    def _fix_glob(m: re.Match) -> str:
        flag, path = m.group(1), m.group(2)
        warnings.append(
            CommandWarning(
                category="unquoted_glob",
                message=f"Glob in {flag} should be quoted: "
                f'{flag} {path} \u2192 {flag} "{path}"',
            )
        )
        return f'{flag} "{path}"'

    cmd = unquoted_glob.sub(_fix_glob, cmd)

    # 4. Check: unbalanced quotes
    for i, line in enumerate(joined.split(" "), 1):
        # Simple check: count quotes
        pass  # complex to do reliably; skip for now

    # 5. Check: -i/-o flag at very end with no value
    if re.search(r"-[io]\s*$", joined.rstrip()):
        warnings.append(
            CommandWarning(
                category="trailing_flag",
                message="Command ends with a flag (-i/-o) that has no value",
            )
        )

    return cmd, warnings


def extract_datalad_cmds(script_path: Path) -> list[ExtractedCommand]:
    """Extract all valid ``datalad run`` commands from *script_path*.

    Each command is validated and annotated with a label (the descriptive
    text preceding it in the docstring) and any auto-fix warnings.
    Invalid matches (e.g. ``datalad run (comment):``) are filtered out.
    """
    content = script_path.read_text()
    results: list[ExtractedCommand] = []
    for m in re.finditer(
        r"^[ \t]*datalad run(?=[ \t\\]|$)", content, re.MULTILINE
    ):
        raw = _extract_one_cmd(content, m.start())
        if not _is_valid_command(raw):
            continue
        label = _extract_label(content, m.start())
        validated, warnings = validate_command(raw)
        results.append(
            ExtractedCommand(
                raw=raw,
                label=label,
                validated=validated,
                warnings=warnings,
            )
        )
    return results


def score_commands(
    cmds: list[ExtractedCommand], cwd: Path
) -> list[ExtractedCommand]:
    """Score commands by how well their concrete paths match *cwd*.

    Sets ``score`` and ``is_best`` on each command.  Returns all commands
    sorted by score (descending), with the best match first.
    """
    if not cmds:
        return cmds

    for cmd in cmds:
        score = 0
        for m in re.finditer(r'-[io]\s+"([^"]+)"', cmd.validated):
            p = m.group(1)
            if "{" in p or "*" in p or "?" in p:
                continue
            if (cwd / p).exists():
                score += 1
        cmd.score = score

    cmds.sort(key=lambda c: -c.score)
    cmds[0].is_best = True
    return cmds


def pick_cmd_for_cwd(cmds: list[ExtractedCommand], cwd: Path) -> str:
    """Pick the command whose concrete paths best match *cwd*.

    Backward-compatible wrapper around :func:`score_commands`.
    """
    scored = score_commands(cmds, cwd)
    return scored[0].validated
