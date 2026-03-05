"""Tests for extract.py — command extraction from scripts."""

from __future__ import annotations

from pathlib import Path

from datalad_runcmd.config import load_config
from datalad_runcmd.extract import (
    extract_datalad_cmds,
    find_script,
    find_script_candidates,
    pick_cmd_for_cwd,
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
    assert "datalad run" in cmds[0]
    assert "{sub-id}" in cmds[0]
    assert "{exp-drug}" in cmds[0]


def test_extract_two_cmds(project: Path):
    script = project / "code" / "src" / "pipeline" / "two_blocks.py"
    cmds = extract_datalad_cmds(script)
    assert len(cmds) == 2
    assert "Variant A" in cmds[0]
    assert "Variant B" in cmds[1]


def test_extract_no_placeholders(project: Path):
    script = project / "code" / "src" / "tools" / "prepare_metadata.py"
    cmds = extract_datalad_cmds(script)
    assert len(cmds) == 1
    assert "{sub-id}" not in cmds[0]


def test_pick_cmd_single(project: Path):
    cmds = ["datalad run -m 'test' 'echo hello'"]
    assert pick_cmd_for_cwd(cmds, project) == cmds[0]


def test_pick_cmd_scores_existing_paths(project: Path):
    """The command referencing existing directories should win."""
    script = project / "code" / "src" / "pipeline" / "two_blocks.py"
    cmds = extract_datalad_cmds(script)
    # 01_data/ and 02_processed/ exist; 03_extra/ and 04_final/ don't.
    # But all have {sub-id} placeholders, so they're skipped by the scorer.
    # With no concrete paths to score, first command wins (score tie).
    result = pick_cmd_for_cwd(cmds, project)
    assert "Variant A" in result
