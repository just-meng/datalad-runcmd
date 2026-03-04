"""Load project configuration from .datalad/runcmd.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class PlaceholderSpec:
    """Specification for resolving a single placeholder."""

    type: Literal["lookup", "prefix", "enum"]
    prefix: str = ""
    # lookup-specific
    file: str = ""
    column: int = 0
    skip_header: bool = True
    scan_dirs: list[str] = field(default_factory=list)
    # enum-specific
    values: list[str] = field(default_factory=list)


@dataclass
class Config:
    """Project-level runcmd configuration."""

    root: Path
    script_dirs: list[Path]
    placeholders: dict[str, PlaceholderSpec]


def _parse_placeholder(name: str, table: dict) -> PlaceholderSpec:
    ptype = table.get("type", "prefix")
    return PlaceholderSpec(
        type=ptype,
        prefix=table.get("prefix", ""),
        file=table.get("file", ""),
        column=table.get("column", 0),
        skip_header=table.get("skip_header", True),
        scan_dirs=table.get("scan_dirs", []),
        values=table.get("values", []),
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
