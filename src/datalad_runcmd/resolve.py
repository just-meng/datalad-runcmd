"""Generic placeholder resolution engine, driven by PlaceholderSpec."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import PlaceholderSpec


class ResolutionError(Exception):
    """Raised when a placeholder argument cannot be resolved."""


# Separator characters used for word-boundary affix trimming
_SEPS = frozenset("-_.")


# ── file reading ──────────────────────────────────────────────────────────────


def _read_file(path: Path, spec: PlaceholderSpec) -> list[str]:
    """Read candidate values from *path*.

    Format is auto-detected by extension unless ``spec.separator`` is set:

    * ``.json`` — JSON array (elements) or object (keys)
    * ``.tsv``  — tab-separated; reads ``spec.column`` / ``spec.column_name``
    * ``.csv``  — comma-separated; same column selection
    * anything else — one value per line (plain text)

    Set ``spec.separator`` to force a specific delimiter for delimited files.
    """
    suffix = path.suffix.lower()

    if suffix == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return [str(v) for v in data if v is not None]
        if isinstance(data, dict):
            return list(data.keys())
        return []

    sep = spec.separator
    if not sep:
        if suffix == ".tsv":
            sep = "\t"
        elif suffix == ".csv":
            sep = ","

    lines = path.read_text().splitlines()

    if not sep:
        # Plain text: one value per line
        start = 1 if spec.skip_header else 0
        return [ln.strip() for ln in lines[start:] if ln.strip()]

    # Delimited file
    col_idx = spec.column
    start = 0
    if spec.skip_header and lines:
        header = lines[0].split(sep)
        if spec.column_name and spec.column_name in header:
            col_idx = header.index(spec.column_name)
        start = 1

    result: list[str] = []
    for line in lines[start:]:
        parts = line.split(sep)
        if len(parts) > col_idx:
            val = parts[col_idx].strip()
            if val:
                result.append(val)
    return result


# ── candidate collection ──────────────────────────────────────────────────────


def _collect_candidates(spec: PlaceholderSpec, root: Path) -> list[str]:
    """Gather all candidate values from every configured source."""
    candidates: list[str] = list(spec.values)

    if spec.file:
        path = root / spec.file
        if path.is_file():
            candidates.extend(_read_file(path, spec))

    for dirname in spec.scan_dirs:
        stage = root / dirname
        if stage.is_dir():
            for d in stage.iterdir():
                if d.is_dir():
                    candidates.append(d.name)

    # Deduplicate preserving insertion order
    seen: set[str] = set()
    result: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


# ── unique-part extraction ────────────────────────────────────────────────────


def _trim_prefix(raw: str) -> str:
    """Trim *raw* common prefix back to the last separator boundary.

    Examples::

        "sub-00"  → "sub-"   (last '-' at index 3)
        "exp-"    → "exp-"   (already ends with separator)
        "abc"     → "abc"    (no separator: keep all)
    """
    for i in range(len(raw) - 1, -1, -1):
        if raw[i] in _SEPS:
            return raw[:i + 1]
    return raw


def _trim_suffix(raw: str) -> str:
    """Trim *raw* common suffix forward to the first separator boundary.

    Examples::

        "-01"  → "-01"   (starts with '-')
        "v2"   → "v2"    (no separator: keep all)
    """
    for i, ch in enumerate(raw):
        if ch in _SEPS:
            return raw[i:]
    return raw


def _unique_parts(candidates: list[str]) -> dict[str, str]:
    """Map each candidate to its *unique part* by stripping the common affix.

    The common prefix and suffix shared by *all* candidates are auto-detected
    (case-insensitively) and trimmed to the nearest separator so that whole
    identifier components are preserved.

    For a single candidate the full string is returned unchanged — there is
    nothing to compare against and the user's input is validated against the
    full value.

    Examples::

        ["sub-001A", "sub-002B"] → {"sub-001A": "001A", "sub-002B": "002B"}
        ["ses-pre-01", "ses-mid-01"] → {"ses-pre-01": "pre", "ses-mid-01": "mid"}
    """
    if len(candidates) <= 1:
        return {c: c for c in candidates}

    lower = [c.lower() for c in candidates]
    pre = _trim_prefix(os.path.commonprefix(lower))
    suf = _trim_suffix(os.path.commonprefix([s[::-1] for s in lower])[::-1])

    result: dict[str, str] = {}
    for c in candidates:
        end = len(c) - len(suf) if suf else len(c)
        unique = c[len(pre):end]
        result[c] = unique if unique else c  # safety: never return empty
    return result


# ── matching ──────────────────────────────────────────────────────────────────


def _score_candidate(arg: str, candidate: str, unique: str) -> float | None:
    """Score how specifically *arg* identifies *candidate* (case-insensitive).

    Returns a value in ``(0, 1]`` or ``None`` (no match).

    Priority:

    1. Exact match against the **full candidate** → 1.0
       (so users can always type the complete identifier)
    2. Exact match against the **unique part** → 1.0
    3. *arg* is a substring of the **unique part** → ``len(arg) / len(unique)``
    """
    al = arg.lower()
    if al == candidate.lower():
        return 1.0
    ul = unique.lower()
    if al == ul:
        return 1.0
    if al in ul:
        return len(arg) / len(unique)
    return None


# ── public API ────────────────────────────────────────────────────────────────


def resolve_placeholder(arg: str, spec: PlaceholderSpec, root: Path) -> str:
    """Resolve *arg* according to *spec* and return the fully-resolved value.

    **Algorithm**

    1. Collect candidates from all configured sources (``values``, ``file``,
       ``scan_dirs``).
    2. If *no* sources are configured → raw substitution: return
       ``prefix + arg`` (adding the prefix only when missing).
    3. Filter candidates by ``spec.prefix`` (keep only those that start with
       the prefix).
    4. Auto-detect the common prefix/suffix shared by all candidates and
       derive each candidate's *unique part* (trimmed to word boundaries).
    5. Score: exact full-string or unique-part match = 1.0; substring in
       unique part = ``len(arg) / len(unique_part)``.
    6. Return the unique highest-scoring candidate.
    7. True ties (same score across multiple candidates) → raise
       :class:`ResolutionError` listing all options.
    """
    has_lookup = bool(spec.values or spec.file or spec.scan_dirs)
    candidates = _collect_candidates(spec, root)

    if not candidates:
        if has_lookup:
            raise ResolutionError(
                f"No candidates available for '{arg}' — configured sources "
                f"returned nothing "
                f"(file={spec.file!r}, scan_dirs={spec.scan_dirs!r})"
            )
        # No lookup configured: raw substitution with optional prefix
        if spec.prefix and not arg.startswith(spec.prefix):
            return spec.prefix + arg
        return arg

    # Filter by prefix
    if spec.prefix:
        candidates = [c for c in candidates if c.startswith(spec.prefix)]
        if not candidates:
            raise ResolutionError(
                f"No candidates start with prefix {spec.prefix!r}"
            )

    unique = _unique_parts(candidates)

    scored = [(c, _score_candidate(arg, c, unique[c])) for c in candidates]
    scored = [(c, s) for c, s in scored if s is not None]

    if not scored:
        avail = ", ".join(sorted(unique.values()))
        raise ResolutionError(
            f"No candidate matches '{arg}'. "
            f"Available identifiers: {avail}"
        )

    best_score = max(s for _, s in scored)
    best = [c for c, s in scored if s == best_score]

    if len(best) == 1:
        return best[0]

    raise ResolutionError(
        f"Ambiguous '{arg}' — {len(best)} candidates match equally:\n"
        + "\n".join(f"  {c}" for c in sorted(best))
        + "\nPlease be more specific."
    )
