"""Tests for cli.py — end-to-end CLI tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from datalad_runcmd.cli import main


def test_cli_with_placeholders(project: Path, capsys, monkeypatch):
    monkeypatch.chdir(project)
    main(["process", "A", "Saline"])
    out = capsys.readouterr().out.strip()
    assert "sub-001A" in out
    assert "exp-Saline" in out
    assert "datalad run" in out


def test_cli_orphaned_config_key_warning(project: Path, capsys, monkeypatch):
    """Config keys not used by any script produce a warning on stderr."""
    # Add a config key that no script references
    toml = project / ".datalad" / "runcmd.toml"
    toml.write_text(toml.read_text() + '\n[runcmd.placeholders.exp-id]\nprefix = "exp-"\n')
    monkeypatch.chdir(project)
    main(["process", "A", "Saline"])
    err = capsys.readouterr().err
    assert "exp-id" in err
    assert "Warning" in err


def test_cli_no_placeholders(project: Path, capsys, monkeypatch):
    monkeypatch.chdir(project)
    main(["prepare_metadata"])
    out = capsys.readouterr().out.strip()
    assert "datalad run" in out
    assert "{sub-id}" not in out


def test_cli_missing_args(project: Path, monkeypatch):
    monkeypatch.chdir(project)
    with pytest.raises(SystemExit):
        main(["process", "A"])  # missing experiment


def test_cli_script_not_found(project: Path, monkeypatch):
    monkeypatch.chdir(project)
    with pytest.raises(SystemExit, match="not found"):
        main(["nonexistent"])


def test_cli_fuzzy_suggestion(project: Path, monkeypatch):
    """When exact script not found, fuzzy candidates with runcmd blocks shown."""
    monkeypatch.chdir(project)
    with pytest.raises(SystemExit) as exc_info:
        main(["proc"])  # matches "process"
    assert "Did you mean" in str(exc_info.value)
    assert "process.py" in str(exc_info.value)


def test_cli_no_config_warns_and_resolves(tmp_path: Path, capsys, monkeypatch):
    """Without runcmd.toml, placeholders are substituted raw with a warning."""
    (tmp_path / "myscript.py").write_text('''\
"""My script.

    datalad run \\
        -m "Run {subject} {session}" \\
        "echo {subject} {session}"
"""
''')
    monkeypatch.chdir(tmp_path)
    main(["myscript", "sub-01", "ses-pre"])
    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "runcmd.toml" in captured.err
    assert "sub-01" in captured.out
    assert "ses-pre" in captured.out
    assert "{subject}" not in captured.out


def test_cli_no_config_script_not_found(tmp_path: Path, capsys, monkeypatch):
    """Without runcmd.toml and no matching script, exits with useful error."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="not found"):
        main(["anything"])


def test_cli_unconfigured_placeholder(project: Path, capsys, monkeypatch):
    """Placeholders not in config are substituted raw."""
    script_dir = project / "code" / "src" / "pipeline"
    (script_dir / "custom.py").write_text('''\
"""Custom script.

    datalad run \\
        -m "Custom {label}" \\
        "echo {label}"
"""
''')
    monkeypatch.chdir(project)
    main(["custom", "hello"])
    out = capsys.readouterr().out.strip()
    assert "hello" in out
    assert "{label}" not in out


def test_cli_datalad_placeholders_ignored(project: Path, capsys, monkeypatch):
    """DataLad's {inputs} and {outputs} are left for datalad run to resolve."""
    script_dir = project / "code" / "src" / "pipeline"
    (script_dir / "with_io.py").write_text('''\
"""Script using datalad placeholders.

    datalad run \\
        -m "Run {sub-id}" \\
        -i "data/{sub-id}/" \\
        -o "out/{sub-id}/" \\
        "./code/src/pipeline/with_io.py {inputs} {outputs}"
"""
''')
    monkeypatch.chdir(project)
    main(["with_io", "A"])
    out = capsys.readouterr().out.strip()
    assert "sub-001A" in out
    assert "{inputs}" in out
    assert "{outputs}" in out


def test_cli_from_subdirectory(project: Path, capsys, monkeypatch):
    """Config is found by walking up from cwd."""
    subdir = project / "01_data" / "sub-001A"
    monkeypatch.chdir(subdir)
    main(["process", "A", "LSD"])
    out = capsys.readouterr().out.strip()
    assert "sub-001A" in out
    assert "exp-LSD" in out


def test_cli_case_insensitive_lookup_match(project: Path, capsys, monkeypatch):
    """Lookup matching is case-insensitive (raw-mode placeholders are not affected)."""
    monkeypatch.chdir(project)
    # 'a' lower-case still resolves to 'sub-001A' via TSV lookup
    main(["process", "a", "Saline"])
    out = capsys.readouterr().out.strip()
    assert "sub-001A" in out


# ── multi-command output ─────────────────────────────────────────────────────


def test_cli_multi_command_shows_all(project: Path, capsys, monkeypatch):
    """When a script has multiple commands, all are printed with headers."""
    monkeypatch.chdir(project)
    main(["two_blocks", "A"])
    out = capsys.readouterr().out
    assert "Variant A" in out
    assert "Variant B" in out
    # Both commands should appear in output
    assert out.count("datalad run") == 2
    # Best match indicator
    assert "best match" in out


def test_cli_multi_command_resolves_all(project: Path, capsys, monkeypatch):
    """Placeholders are resolved in all commands, not just the best match."""
    monkeypatch.chdir(project)
    main(["two_blocks", "A"])
    out = capsys.readouterr().out
    # sub-id should be resolved in both commands
    assert "sub-001A" in out
    assert "{sub-id}" not in out


# ── validation warnings in CLI ───────────────────────────────────────────────


def test_cli_glob_warning_on_stderr(tmp_path: Path, capsys, monkeypatch):
    """Unquoted glob patterns produce a warning on stderr."""
    (tmp_path / "script.py").write_text('''\
"""Script.

    datalad run \\
        -m "msg" \\
        -i data/*.tif \\
        "echo run"
"""
''')
    monkeypatch.chdir(tmp_path)
    main(["script"])
    captured = capsys.readouterr()
    assert "unquoted_glob" in captured.err or "Glob" in captured.err


def test_cli_datalad_run_comment_rejected(tmp_path: Path, monkeypatch):
    """A 'datalad run (comment):' line is not treated as a command."""
    (tmp_path / "script.py").write_text('''\
"""Docs.

datalad run (manual ROI pipeline):
"""
''')
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="no 'datalad run' command found"):
        main(["script"])
