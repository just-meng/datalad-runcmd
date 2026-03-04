"""Tests for resolve.py — placeholder resolution engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from datalad_runcmd.config import PlaceholderSpec, load_config
from datalad_runcmd.resolve import ResolutionError, resolve_placeholder


# ── raw mode (no lookup sources) ─────────────────────────────────────────────


def test_raw_adds_prefix():
    spec = PlaceholderSpec(prefix="exp-")
    assert resolve_placeholder("Saline", spec, Path("/dummy")) == "exp-Saline"


def test_raw_passthrough_when_prefix_present():
    spec = PlaceholderSpec(prefix="exp-")
    assert resolve_placeholder("exp-Saline", spec, Path("/dummy")) == "exp-Saline"


def test_raw_no_prefix():
    spec = PlaceholderSpec()
    assert resolve_placeholder("anything", spec, Path("/dummy")) == "anything"


# ── values list ───────────────────────────────────────────────────────────────


def test_values_exact_match():
    spec = PlaceholderSpec(values=["a", "b", "c"])
    assert resolve_placeholder("b", spec, Path("/dummy")) == "b"


def test_values_with_prefix_substring():
    spec = PlaceholderSpec(prefix="mode-", values=["mode-fast", "mode-slow"])
    assert resolve_placeholder("fast", spec, Path("/dummy")) == "mode-fast"


def test_values_no_match():
    spec = PlaceholderSpec(values=["a", "b"])
    with pytest.raises(ResolutionError, match="No candidate matches"):
        resolve_placeholder("z", spec, Path("/dummy"))


def test_values_ambiguous():
    spec = PlaceholderSpec(values=["run-fast", "run-faster"])
    # 'fast' is a substring of both 'run-fast' (score=4/8=0.5) and
    # 'run-faster' (score=4/10=0.4) — not tied, 'run-fast' wins
    assert resolve_placeholder("fast", spec, Path("/dummy")) == "run-fast"


def test_values_true_tie_raises():
    spec = PlaceholderSpec(values=["sub-001A", "sub-002A"])
    with pytest.raises(ResolutionError, match="Ambiguous"):
        resolve_placeholder("A", spec, Path("/dummy"))


def test_values_case_insensitive():
    spec = PlaceholderSpec(values=["exp-Saline", "exp-LSD"])
    assert resolve_placeholder("saline", spec, Path("/dummy")) == "exp-Saline"


# ── TSV lookup ────────────────────────────────────────────────────────────────


def test_lookup_full_id_exact(project: Path):
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
    with pytest.raises(ResolutionError, match="No candidate matches"):
        resolve_placeholder("Z", spec, project)


def test_lookup_fallback_to_dirs(project: Path):
    """When TSV is missing, fall back to directory scan."""
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    (project / "inputs" / "subjects.tsv").unlink()
    assert resolve_placeholder("B", spec, project) == "sub-002B"


def test_lookup_ambiguous(project: Path):
    """If multiple subjects share a suffix, raise with all options listed."""
    for stage in ["01_data", "02_processed"]:
        (project / stage / "sub-999A").mkdir()
    tsv = project / "inputs" / "subjects.tsv"
    tsv.write_text(tsv.read_text() + "sub-999A\t40\tF\n")

    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    with pytest.raises(ResolutionError, match="Ambiguous"):
        resolve_placeholder("A", spec, project)


def test_lookup_best_score_wins(project: Path):
    """A longer, more specific arg should uniquely identify even when a shorter
    arg would be ambiguous."""
    for stage in ["01_data", "02_processed"]:
        (project / stage / "sub-999A").mkdir()
    tsv = project / "inputs" / "subjects.tsv"
    tsv.write_text(tsv.read_text() + "sub-999A\t40\tF\n")

    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    # "001A" only matches "sub-001A" (score 4/8=0.5), not "sub-999A"
    assert resolve_placeholder("001A", spec, project) == "sub-001A"


# ── generic file formats ──────────────────────────────────────────────────────


def test_csv_file(tmp_path: Path):
    csv = tmp_path / "items.csv"
    csv.write_text("id,label\nitem-001,foo\nitem-002,bar\n")
    spec = PlaceholderSpec(file="items.csv", column=0, skip_header=True)
    assert resolve_placeholder("001", spec, tmp_path) == "item-001"


def test_plaintext_file(tmp_path: Path):
    lst = tmp_path / "names.txt"
    lst.write_text("alice\nbob\ncharlie\n")
    spec = PlaceholderSpec(file="names.txt", skip_header=False)
    assert resolve_placeholder("bob", spec, tmp_path) == "bob"


def test_json_array_file(tmp_path: Path):
    jf = tmp_path / "sessions.json"
    jf.write_text(json.dumps(["ses-pre", "ses-post", "ses-follow"]))
    spec = PlaceholderSpec(file="sessions.json")
    assert resolve_placeholder("post", spec, tmp_path) == "ses-post"


def test_json_object_keys(tmp_path: Path):
    jf = tmp_path / "mapping.json"
    jf.write_text(json.dumps({"sub-001": "Alice", "sub-002": "Bob"}))
    spec = PlaceholderSpec(file="mapping.json")
    assert resolve_placeholder("001", spec, tmp_path) == "sub-001"


def test_column_name_selection(tmp_path: Path):
    tsv = tmp_path / "data.tsv"
    tsv.write_text("participant_id\tage\tsex\nsub-001A\t25\tM\nsub-002B\t30\tF\n")
    spec = PlaceholderSpec(
        file="data.tsv", column_name="participant_id", skip_header=True, prefix="sub-"
    )
    assert resolve_placeholder("001A", spec, tmp_path) == "sub-001A"


def test_missing_file_with_scan_dirs_fallback(tmp_path: Path):
    """If the TSV is absent but scan_dirs works, resolution still succeeds."""
    stage = tmp_path / "subjects"
    stage.mkdir()
    (stage / "sub-001A").mkdir()
    spec = PlaceholderSpec(
        file="nonexistent.tsv", scan_dirs=["subjects"], prefix="sub-"
    )
    assert resolve_placeholder("001A", spec, tmp_path) == "sub-001A"


def test_no_candidates_from_configured_sources_raises(tmp_path: Path):
    """If sources are configured but return nothing, raise ResolutionError."""
    spec = PlaceholderSpec(file="missing.tsv", scan_dirs=["empty_dir"])
    with pytest.raises(ResolutionError, match="No candidates available"):
        resolve_placeholder("anything", spec, tmp_path)
