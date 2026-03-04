"""Tests for resolve.py — placeholder resolution engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from datalad_runcmd.config import PlaceholderSpec, load_config
from datalad_runcmd.resolve import ResolutionError, resolve_placeholder


# ── prefix type ──────────────────────────────────────────────────────────────


def test_prefix_adds_missing():
    spec = PlaceholderSpec(type="prefix", prefix="exp-")
    assert resolve_placeholder("Saline", spec, Path("/dummy")) == "exp-Saline"


def test_prefix_passthrough():
    spec = PlaceholderSpec(type="prefix", prefix="exp-")
    assert resolve_placeholder("exp-Saline", spec, Path("/dummy")) == "exp-Saline"


def test_prefix_empty():
    spec = PlaceholderSpec(type="prefix", prefix="")
    assert resolve_placeholder("anything", spec, Path("/dummy")) == "anything"


# ── enum type ────────────────────────────────────────────────────────────────


def test_enum_valid():
    spec = PlaceholderSpec(type="enum", values=["a", "b", "c"])
    assert resolve_placeholder("b", spec, Path("/dummy")) == "b"


def test_enum_with_prefix():
    spec = PlaceholderSpec(type="enum", prefix="mode-", values=["mode-fast", "mode-slow"])
    assert resolve_placeholder("fast", spec, Path("/dummy")) == "mode-fast"


def test_enum_invalid():
    spec = PlaceholderSpec(type="enum", values=["a", "b"])
    with pytest.raises(ResolutionError, match="not one of"):
        resolve_placeholder("z", spec, Path("/dummy"))


# ── lookup type ──────────────────────────────────────────────────────────────


def test_lookup_full_id_passthrough(project: Path):
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    assert resolve_placeholder("sub-001A", spec, project) == "sub-001A"


def test_lookup_suffix_match_via_tsv(project: Path):
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    assert resolve_placeholder("A", spec, project) == "sub-001A"


def test_lookup_longer_suffix(project: Path):
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    assert resolve_placeholder("001A", spec, project) == "sub-001A"


def test_lookup_no_match(project: Path):
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    with pytest.raises(ResolutionError, match="No entry found"):
        resolve_placeholder("Z", spec, project)


def test_lookup_fallback_to_dirs(project: Path):
    """When TSV is missing, fall back to directory scan."""
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    # Remove the TSV file
    (project / "inputs" / "subjects.tsv").unlink()
    assert resolve_placeholder("B", spec, project) == "sub-002B"


def test_lookup_ambiguous(project: Path):
    """If multiple subjects share a suffix, raise an error."""
    # Add an extra subject ending in 'A'
    for stage in ["01_data", "02_processed"]:
        (project / stage / "sub-999A").mkdir()
    # Also add to TSV
    tsv = project / "inputs" / "subjects.tsv"
    tsv.write_text(tsv.read_text() + "sub-999A\t40\tF\n")

    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    with pytest.raises(ResolutionError, match="Ambiguous"):
        resolve_placeholder("A", spec, project)
