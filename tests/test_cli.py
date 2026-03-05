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


def test_cli_no_config(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="runcmd.toml"):
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
