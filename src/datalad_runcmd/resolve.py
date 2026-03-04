"""Generic placeholder resolution engine, driven by PlaceholderSpec."""

from __future__ import annotations

from pathlib import Path

from .config import PlaceholderSpec


class ResolutionError(Exception):
    """Raised when a placeholder argument cannot be resolved."""


def _lookup_from_file(arg: str, spec: PlaceholderSpec, root: Path) -> str | None:
    """Try to resolve *arg* by scanning a TSV file."""
    if not spec.file:
        return None
    path = root / spec.file
    if not path.is_file():
        return None

    entries: list[str] = []
    with open(path) as f:
        if spec.skip_header:
            next(f, None)
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) > spec.column:
                val = parts[spec.column]
                if not spec.prefix or val.startswith(spec.prefix):
                    entries.append(val)
    return _suffix_match(arg, entries, spec.prefix)


def _lookup_from_dirs(arg: str, spec: PlaceholderSpec, root: Path) -> str | None:
    """Try to resolve *arg* by scanning directories."""
    if not spec.scan_dirs:
        return None

    seen: set[str] = set()
    for dirname in spec.scan_dirs:
        stage_dir = root / dirname
        if stage_dir.is_dir():
            for d in stage_dir.iterdir():
                if d.is_dir() and d.name.startswith(spec.prefix):
                    seen.add(d.name)
    if not seen:
        return None
    return _suffix_match(arg, sorted(seen), spec.prefix)


def _suffix_match(arg: str, candidates: list[str], prefix: str) -> str | None:
    """Find a unique candidate whose suffix matches *arg*."""
    matches = [c for c in candidates if c.endswith(arg)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ResolutionError(
            f"Ambiguous '{arg}' — multiple entries match:\n"
            + "\n".join(f"  {m}" for m in sorted(matches))
        )
    return None


def resolve_placeholder(
    arg: str, spec: PlaceholderSpec, root: Path
) -> str:
    """Resolve *arg* according to *spec*, returning the full value.

    Dispatches on ``spec.type``:

    - ``"lookup"``: try file first, then directory scan, suffix-match
    - ``"prefix"``: just prepend prefix if missing
    - ``"enum"``: validate against allowed values
    """
    if spec.type == "prefix":
        if spec.prefix and not arg.startswith(spec.prefix):
            return spec.prefix + arg
        return arg

    if spec.type == "enum":
        if arg not in spec.values:
            prefixed = spec.prefix + arg if spec.prefix else arg
            if prefixed not in spec.values:
                raise ResolutionError(
                    f"'{arg}' is not one of: {', '.join(spec.values)}"
                )
            return prefixed
        return arg

    if spec.type == "lookup":
        # Already fully qualified?
        if spec.prefix and arg.startswith(spec.prefix):
            return arg

        # Try TSV file first, then directory scan
        result = _lookup_from_file(arg, spec, root)
        if result is not None:
            return result

        result = _lookup_from_dirs(arg, spec, root)
        if result is not None:
            return result

        raise ResolutionError(
            f"No entry found matching '{arg}' "
            f"(checked file={spec.file!r}, scan_dirs={spec.scan_dirs})"
        )

    raise ResolutionError(f"Unknown placeholder type: {spec.type!r}")
