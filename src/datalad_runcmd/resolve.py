"""Generic placeholder resolution engine, driven by PlaceholderSpec."""

from __future__ import annotations

import json
from pathlib import Path

from .config import PlaceholderSpec


class ResolutionError(Exception):
    """Raised when a placeholder argument cannot be resolved."""


# ── file readers ──────────────────────────────────────────────────────────────


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


# ── matching ──────────────────────────────────────────────────────────────────


def _score_match(arg: str, candidate: str) -> float | None:
    """Score how specifically *arg* identifies *candidate* (case-insensitive suffix match).

    Returns a value in ``(0, 1]`` — higher means more specific — or ``None``
    when there is no match at all.

    * Exact (case-insensitive) match → 1.0
    * *arg* is a suffix of *candidate* → ``len(arg) / len(candidate)``

    Suffix matching is used (not arbitrary substring) to avoid false positives
    where the arg accidentally matches a common prefix shared by all candidates
    (e.g. 'b' matching the 'b' in 'sub-' for every 'sub-*' identifier).
    """
    al = arg.lower()
    cl = candidate.lower()
    if al == cl:
        return 1.0
    if cl.endswith(al):
        return len(arg) / len(candidate)
    return None


# ── public API ────────────────────────────────────────────────────────────────


def resolve_placeholder(arg: str, spec: PlaceholderSpec, root: Path) -> str:
    """Resolve *arg* according to *spec* and return the fully-resolved value.

    **Algorithm**

    1. Collect candidates from all configured sources (``values``, ``file``,
       ``scan_dirs``).
    2. If *no* sources are configured → raw substitution: return
       ``prefix + arg`` (adding the prefix only when it is missing).
    3. Filter candidates by ``spec.prefix`` (keep only those that start with
       the prefix).
    4. Score each candidate against *arg* using case-insensitive substring
       matching.  Score = ``len(arg) / len(candidate)``; exact match = 1.0.
    5. Return the unique highest-scoring candidate.
    6. If multiple candidates share the top score (true tie), list them all
       and raise :class:`ResolutionError` asking the user to be more specific.
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

    # Keep only candidates that match the configured prefix
    if spec.prefix:
        candidates = [c for c in candidates if c.startswith(spec.prefix)]

    scored = [(c, _score_match(arg, c)) for c in candidates]
    scored = [(c, s) for c, s in scored if s is not None]

    if not scored:
        details = ", ".join(
            filter(None, [
                f"file={spec.file!r}" if spec.file else "",
                f"scan_dirs={spec.scan_dirs}" if spec.scan_dirs else "",
                f"values={spec.values}" if spec.values else "",
            ])
        )
        raise ResolutionError(
            f"No candidate matches '{arg}'"
            + (f" ({details})" if details else "")
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
