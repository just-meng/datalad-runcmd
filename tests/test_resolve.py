"""Tests for resolve.py — placeholder resolution engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from datalad_runcmd.config import PlaceholderSpec, load_config
from datalad_runcmd.resolve import ResolutionError, _unique_parts, resolve_placeholder


# ── unique-part extraction ────────────────────────────────────────────────────


def test_unique_parts_strips_common_prefix():
    parts = _unique_parts(["sub-001A", "sub-002B", "sub-003C"])
    assert parts == {"sub-001A": "001A", "sub-002B": "002B", "sub-003C": "003C"}


def test_unique_parts_strips_common_suffix():
    parts = _unique_parts(["ses-pre-01", "ses-mid-01", "ses-post-01"])
    assert parts == {"ses-pre-01": "pre", "ses-mid-01": "mid", "ses-post-01": "post"}


def test_unique_parts_strips_both_affixes():
    parts = _unique_parts(["run-fast-v2", "run-slow-v2"])
    assert parts == {"run-fast-v2": "fast", "run-slow-v2": "slow"}


def test_unique_parts_single_candidate():
    parts = _unique_parts(["sub-001A"])
    assert parts == {"sub-001A": "sub-001A"}


def test_unique_parts_no_common_affix():
    parts = _unique_parts(["alice", "bob", "charlie"])
    assert parts == {"alice": "alice", "bob": "bob", "charlie": "charlie"}


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


def test_values_substring_match():
    spec = PlaceholderSpec(values=["mode-fast", "mode-slow"])
    assert resolve_placeholder("fast", spec, Path("/dummy")) == "mode-fast"


def test_values_full_id_match():
    """User can always type the full candidate and get exact match."""
    spec = PlaceholderSpec(values=["mode-fast", "mode-slow"])
    assert resolve_placeholder("mode-fast", spec, Path("/dummy")) == "mode-fast"


def test_values_case_insensitive():
    spec = PlaceholderSpec(values=["exp-Saline", "exp-LSD"])
    assert resolve_placeholder("saline", spec, Path("/dummy")) == "exp-Saline"


def test_values_no_match():
    spec = PlaceholderSpec(values=["a", "b"])
    with pytest.raises(ResolutionError, match="No candidate"):
        resolve_placeholder("z", spec, Path("/dummy"))


def test_values_best_score_wins():
    """Longer match on the unique part wins over shorter."""
    # unique parts: "fast" vs "faster". "fast" matches "fast" exactly (1.0)
    # and "fast" in "faster" (0.67). Unique winner.
    spec = PlaceholderSpec(values=["run-fast", "run-faster"])
    assert resolve_placeholder("fast", spec, Path("/dummy")) == "run-fast"


def test_values_ambiguous_tie():
    """Arg matching the unique parts of multiple candidates at the same score."""
    # unique parts: "001A" and "002A" → stripping common suffix "A" → "001" and "002"
    # "00" is substring of both with equal score → ambiguous
    spec = PlaceholderSpec(values=["sub-001A", "sub-002A"])
    with pytest.raises(ResolutionError, match="Ambiguous"):
        resolve_placeholder("00", spec, Path("/dummy"))


def test_values_common_suffix_not_a_discriminator():
    """A value that only matches the stripped common suffix yields no match."""
    # Both candidates end with "A"; "A" is stripped as common suffix.
    # The unique parts are "001" and "002" — "A" is not in either.
    spec = PlaceholderSpec(values=["sub-001A", "sub-002A"])
    with pytest.raises(ResolutionError, match="No candidate"):
        resolve_placeholder("A", spec, Path("/dummy"))


# ── TSV lookup ────────────────────────────────────────────────────────────────


def test_lookup_full_id_exact(project: Path):
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    assert resolve_placeholder("sub-001A", spec, project) == "sub-001A"


def test_lookup_unique_part_match(project: Path):
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    assert resolve_placeholder("A", spec, project) == "sub-001A"


def test_lookup_longer_unique_part(project: Path):
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    assert resolve_placeholder("001A", spec, project) == "sub-001A"


def test_lookup_no_match(project: Path):
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    with pytest.raises(ResolutionError, match="No candidate"):
        resolve_placeholder("Z", spec, project)


def test_lookup_fallback_to_dirs(project: Path):
    """When TSV is missing, fall back to directory scan."""
    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    (project / "inputs" / "subjects.tsv").unlink()
    assert resolve_placeholder("B", spec, project) == "sub-002B"


def test_lookup_ambiguous(project: Path):
    """Multiple candidates with matching unique parts → list all and raise."""
    for stage in ["01_data", "02_processed"]:
        (project / stage / "sub-999A").mkdir()
    tsv = project / "inputs" / "subjects.tsv"
    tsv.write_text(tsv.read_text() + "sub-999A\t40\tF\n")

    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    # "A" is in both unique parts "001A" and "999A" at the same score
    with pytest.raises(ResolutionError, match="Ambiguous"):
        resolve_placeholder("A", spec, project)


def test_lookup_best_score_wins(project: Path):
    """Providing more of the unique part selects uniquely even when a shorter
    arg would be ambiguous."""
    for stage in ["01_data", "02_processed"]:
        (project / stage / "sub-999A").mkdir()
    tsv = project / "inputs" / "subjects.tsv"
    tsv.write_text(tsv.read_text() + "sub-999A\t40\tF\n")

    cfg = load_config(project)
    spec = cfg.placeholders["sub-id"]
    # "001A" exactly matches unique part of "sub-001A" (score 1.0)
    assert resolve_placeholder("001A", spec, project) == "sub-001A"


# ── session-style common suffix stripping ─────────────────────────────────────


def test_common_suffix_stripped_for_matching(tmp_path: Path):
    """Candidates with a common version suffix: match via unique middle part."""
    spec = PlaceholderSpec(values=["ses-pre-v2", "ses-post-v2", "ses-mid-v2"])
    # unique parts after stripping "ses-" prefix and "-v2" suffix: pre, post, mid
    assert resolve_placeholder("pre", spec, tmp_path) == "ses-pre-v2"
    assert resolve_placeholder("post", spec, tmp_path) == "ses-post-v2"


# ── generic file formats ──────────────────────────────────────────────────────


def test_csv_file(tmp_path: Path):
    (tmp_path / "items.csv").write_text("id,label\nitem-001,foo\nitem-002,bar\n")
    spec = PlaceholderSpec(file="items.csv", column=0, skip_header=True)
    assert resolve_placeholder("001", spec, tmp_path) == "item-001"


def test_plaintext_file(tmp_path: Path):
    (tmp_path / "names.txt").write_text("alice\nbob\ncharlie\n")
    spec = PlaceholderSpec(file="names.txt", skip_header=False)
    assert resolve_placeholder("bob", spec, tmp_path) == "bob"


def test_json_array_file(tmp_path: Path):
    (tmp_path / "sessions.json").write_text(json.dumps(["ses-pre", "ses-post", "ses-follow"]))
    spec = PlaceholderSpec(file="sessions.json")
    assert resolve_placeholder("post", spec, tmp_path) == "ses-post"


def test_json_object_keys(tmp_path: Path):
    (tmp_path / "mapping.json").write_text(json.dumps({"sub-001": "Alice", "sub-002": "Bob"}))
    spec = PlaceholderSpec(file="mapping.json")
    assert resolve_placeholder("001", spec, tmp_path) == "sub-001"


def test_column_name_selection(tmp_path: Path):
    (tmp_path / "data.tsv").write_text(
        "participant_id\tage\tsex\nsub-001A\t25\tM\nsub-002B\t30\tF\n"
    )
    spec = PlaceholderSpec(
        file="data.tsv", column_name="participant_id", skip_header=True, prefix="sub-"
    )
    assert resolve_placeholder("001A", spec, tmp_path) == "sub-001A"


def test_missing_file_with_scan_dirs_fallback(tmp_path: Path):
    stage = tmp_path / "subjects"
    stage.mkdir()
    (stage / "sub-001A").mkdir()
    spec = PlaceholderSpec(file="nonexistent.tsv", scan_dirs=["subjects"], prefix="sub-")
    assert resolve_placeholder("001A", spec, tmp_path) == "sub-001A"


def test_no_candidates_from_configured_sources_raises(tmp_path: Path):
    spec = PlaceholderSpec(file="missing.tsv", scan_dirs=["empty_dir"])
    with pytest.raises(ResolutionError, match="No candidates available"):
        resolve_placeholder("anything", spec, tmp_path)
