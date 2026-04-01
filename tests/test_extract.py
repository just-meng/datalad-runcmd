"""Tests for extract.py — command extraction from scripts."""

from __future__ import annotations

from pathlib import Path

from datalad_runcmd.config import load_config
from datalad_runcmd.extract import (
    ExtractedCommand,
    extract_datalad_cmds,
    find_script,
    find_script_candidates,
    score_commands,
    validate_command,
)


def test_find_script_with_suffix(project: Path):
    cfg = load_config(project)
    assert find_script("process.py", cfg.script_dirs) is not None


def test_find_script_without_suffix(project: Path):
    cfg = load_config(project)
    assert find_script("process", cfg.script_dirs) is not None


def test_find_script_in_second_dir(project: Path):
    cfg = load_config(project)
    result = find_script("prepare_metadata.py", cfg.script_dirs)
    assert result is not None
    assert "tools" in str(result)


def test_find_script_not_found(project: Path):
    cfg = load_config(project)
    assert find_script("nonexistent.py", cfg.script_dirs) is None


def test_find_script_candidates_fuzzy(project: Path):
    cfg = load_config(project)
    # "proc" is a substring of "process"
    candidates = find_script_candidates("proc", cfg.script_dirs)
    assert any("process" in p.name for p in candidates)


def test_find_script_candidates_only_with_runcmd(project: Path):
    """Candidates must have datalad run blocks."""
    script_dir = project / "code" / "src" / "pipeline"
    # Write a script without any datalad run block
    (script_dir / "proc_no_cmd.py").write_text('"""No commands here."""\n')
    cfg = load_config(project)
    candidates = find_script_candidates("proc", cfg.script_dirs)
    assert not any("proc_no_cmd" in p.name for p in candidates)


def test_find_script_candidates_empty_when_no_match(project: Path):
    cfg = load_config(project)
    assert find_script_candidates("xyzzy", cfg.script_dirs) == []


def test_extract_single_cmd(project: Path):
    script = project / "code" / "src" / "pipeline" / "process.py"
    cmds = extract_datalad_cmds(script)
    assert len(cmds) == 1
    assert "datalad run" in cmds[0].validated
    assert "{sub-id}" in cmds[0].validated
    assert "{exp-drug}" in cmds[0].validated


def test_extract_two_cmds(project: Path):
    script = project / "code" / "src" / "pipeline" / "two_blocks.py"
    cmds = extract_datalad_cmds(script)
    assert len(cmds) == 2
    assert "Variant A" in cmds[0].validated
    assert "Variant B" in cmds[1].validated


def test_extract_no_placeholders(project: Path):
    script = project / "code" / "src" / "tools" / "prepare_metadata.py"
    cmds = extract_datalad_cmds(script)
    assert len(cmds) == 1
    assert "{sub-id}" not in cmds[0].validated


def test_score_single(project: Path):
    cmds = [ExtractedCommand(
        raw="datalad run -m 'test' 'echo hello'",
        label="",
        validated="datalad run -m 'test' 'echo hello'",
    )]
    scored = score_commands(cmds, project)
    assert scored[0].validated == cmds[0].validated
    assert scored[0].is_best


def test_score_existing_paths(project: Path):
    """The command referencing existing directories should win."""
    script = project / "code" / "src" / "pipeline" / "two_blocks.py"
    cmds = extract_datalad_cmds(script)
    # 01_data/ and 02_processed/ exist; 03_extra/ and 04_final/ don't.
    # But all have {sub-id} placeholders, so they're skipped by the scorer.
    # With no concrete paths to score, first command wins (score tie).
    scored = score_commands(cmds, project)
    assert "Variant A" in scored[0].validated
    assert scored[0].is_best


# ── label extraction ─────────────────────────────────────────────────────────


def test_extract_labels_from_two_blocks(tmp_path: Path):
    """Labels are extracted from the text preceding each datalad run block."""
    (tmp_path / "script.py").write_text('''\
"""Pipeline with two variants.

    Manual pipeline (uses curated ROIs):
    datalad run \\
        -m "manual" \\
        "echo manual"

    Auto pipeline (uses autosort ROIs):
    datalad run \\
        -m "auto" \\
        "echo auto"
"""
''')
    cmds = extract_datalad_cmds(tmp_path / "script.py")
    assert len(cmds) == 2
    assert cmds[0].label == "Manual pipeline (uses curated ROIs)"
    assert cmds[1].label == "Auto pipeline (uses autosort ROIs)"


def test_extract_label_empty_when_no_preceding_text(tmp_path: Path):
    """No label when datalad run is at the start of the docstring."""
    (tmp_path / "script.py").write_text('''\
"""
    datalad run \\
        -m "msg" \\
        "echo hello"
"""
''')
    cmds = extract_datalad_cmds(tmp_path / "script.py")
    assert len(cmds) == 1
    assert cmds[0].label == ""


# ── validation: false positive filtering ─────────────────────────────────────


def test_reject_datalad_run_comment(tmp_path: Path):
    """'datalad run (some comment):' is not a valid command."""
    (tmp_path / "script.py").write_text('''\
"""Pipeline docs.

datalad run (manual ROI pipeline — iscell files from manual curation):
    datalad run \\
        -m "msg" \\
        "echo hello"
"""
''')
    cmds = extract_datalad_cmds(tmp_path / "script.py")
    assert len(cmds) == 1
    assert "echo hello" in cmds[0].validated


# ── validation: unquoted globs ───────────────────────────────────────────────


def test_validate_unquoted_glob_in_input():
    raw = 'datalad run \\\n    -m "msg" \\\n    -i data/sub-*/*.tif \\\n    "echo run"'
    validated, warnings = validate_command(raw)
    assert '-i "data/sub-*/*.tif"' in validated
    assert any(w.category == "unquoted_glob" for w in warnings)


def test_validate_quoted_glob_no_warning():
    raw = 'datalad run \\\n    -m "msg" \\\n    -i "data/sub-*/*.tif" \\\n    "echo run"'
    validated, warnings = validate_command(raw)
    assert '-i "data/sub-*/*.tif"' in validated
    assert not any(w.category == "unquoted_glob" for w in warnings)


# ── validation: double backslash ─────────────────────────────────────────────


def test_validate_double_backslash():
    raw = "datalad run \\\\\n    -m \"msg\" \\\\\n    \"echo run\""
    validated, warnings = validate_command(raw)
    assert "\\\\" not in validated
    assert any(w.category == "double_backslash" for w in warnings)


# ── validation: missing executable ───────────────────────────────────────────


def test_validate_missing_executable():
    raw = 'datalad run \\\n    -m "msg" \\\n    -o "out/"'
    _, warnings = validate_command(raw)
    assert any(w.category == "missing_executable" for w in warnings)


def test_validate_clean_command():
    raw = 'datalad run \\\n    -m "msg" \\\n    -i "in/*" \\\n    -o "out/" \\\n    "python run.py"'
    _, warnings = validate_command(raw)
    assert len(warnings) == 0


# ── validation: trailing flag ────────────────────────────────────────────────


def test_validate_trailing_flag():
    raw = 'datalad run \\\n    -m "msg" \\\n    -i'
    _, warnings = validate_command(raw)
    assert any(w.category == "trailing_flag" for w in warnings)
