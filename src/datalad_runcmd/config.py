"""Load project configuration from .datalad/runcmd.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PlaceholderSpec:
    """Specification for resolving a single placeholder.

    Candidates are collected from any combination of *values*, *file*, and
    *scan_dirs*.  If no source is configured, the argument is used as-is
    (with an optional *prefix* prepended when missing).

    File formats auto-detected by extension: ``.tsv`` (tab), ``.csv``
    (comma), ``.json`` (array or object-keys), anything else (one value per
    line).  Override with *separator*.  Use *column* (0-indexed) or
    *column_name* to select which field to read from delimited files.
    """

    prefix: str = ""
    # Candidate sources — any combination is valid
    values: list[str] = field(default_factory=list)
    file: str = ""
    column: int = 0
    column_name: str = ""
    separator: str = ""
    skip_header: bool = True
    scan_dirs: list[str] = field(default_factory=list)


@dataclass
class Config:
    """Project-level runcmd configuration."""

    root: Path
    script_dirs: list[Path]
    placeholders: dict[str, PlaceholderSpec]


def _parse_placeholder(name: str, table: dict) -> PlaceholderSpec:
    # 'type' key accepted for backward compat but not used — behaviour is now
    # inferred from which sources are configured.
    return PlaceholderSpec(
        prefix=table.get("prefix", ""),
        values=table.get("values", []),
        file=table.get("file", ""),
        column=table.get("column", 0),
        column_name=table.get("column_name", ""),
        separator=table.get("separator", ""),
        skip_header=table.get("skip_header", True),
        scan_dirs=table.get("scan_dirs", []),
    )


def load_config(cwd: Path | None = None) -> Config:
    """Walk up from *cwd* to find ``.datalad/runcmd.toml`` and parse it."""
    if cwd is None:
        cwd = Path.cwd()
    cwd = cwd.resolve()

    current = cwd
    while True:
        toml_path = current / ".datalad" / "runcmd.toml"
        if toml_path.is_file():
            break
        parent = current.parent
        if parent == current:
            raise FileNotFoundError(
                f"No .datalad/runcmd.toml found in {cwd} or any parent directory"
            )
        current = parent

    with open(toml_path, "rb") as f:
        raw = tomllib.load(f)

    runcmd = raw.get("runcmd", {})
    script_dirs = [current / d for d in runcmd.get("script_dirs", [])]
    placeholders = {
        name: _parse_placeholder(name, spec)
        for name, spec in runcmd.get("placeholders", {}).items()
    }

    return Config(root=current, script_dirs=script_dirs, placeholders=placeholders)
