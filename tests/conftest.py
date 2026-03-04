"""Shared fixtures for datalad-runcmd tests."""

from __future__ import annotations

import pytest
from pathlib import Path

TOML_CONTENT = """\
[runcmd]
script_dirs = ["code/src/pipeline", "code/src/tools"]

[runcmd.placeholders.sub-id]
file = "inputs/subjects.tsv"
column = 0
prefix = "sub-"
skip_header = true
scan_dirs = ["01_data", "02_processed"]

[runcmd.placeholders.exp-drug]
prefix = "exp-"
"""

SCRIPT_WITH_PLACEHOLDERS = '''\
"""Process data for one subject/experiment.

    datalad run \\
        -m "Process {sub-id} {exp-drug}" \\
        -i "01_data/{sub-id}/{exp-drug}/*" \\
        -o "02_processed/{sub-id}/{exp-drug}/" \\
        "python code/src/pipeline/process.py {sub-id} {exp-drug}"
"""
'''

SCRIPT_NO_PLACEHOLDERS = '''\
"""Prepare metadata.

    datalad run \\
        -m "Prepare metadata" \\
        -o "metadata.json" \\
        "python code/src/tools/prepare_metadata.py"
"""
'''

SCRIPT_TWO_BLOCKS = '''\
"""Run pipeline — two variants.

    datalad run \\
        -m "Variant A" \\
        -i "01_data/{sub-id}/*" \\
        -o "02_processed/{sub-id}/" \\
        "python code/src/pipeline/two_blocks.py --mode a {sub-id}"

    datalad run \\
        -m "Variant B" \\
        -i "03_extra/{sub-id}/*" \\
        -o "04_final/{sub-id}/" \\
        "python code/src/pipeline/two_blocks.py --mode b {sub-id}"
"""
'''

SUBJECTS_TSV = """\
participant_id\tage\tsex
sub-001A\t25\tM
sub-002B\t30\tF
sub-003C\t28\tM
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a minimal project layout with config and scripts."""
    # Config
    datalad_dir = tmp_path / ".datalad"
    datalad_dir.mkdir()
    (datalad_dir / "runcmd.toml").write_text(TOML_CONTENT)

    # Scripts
    pipeline_dir = tmp_path / "code" / "src" / "pipeline"
    pipeline_dir.mkdir(parents=True)
    (pipeline_dir / "process.py").write_text(SCRIPT_WITH_PLACEHOLDERS)
    (pipeline_dir / "two_blocks.py").write_text(SCRIPT_TWO_BLOCKS)

    tools_dir = tmp_path / "code" / "src" / "tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "prepare_metadata.py").write_text(SCRIPT_NO_PLACEHOLDERS)

    # Subjects TSV
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    (inputs_dir / "subjects.tsv").write_text(SUBJECTS_TSV)

    # Stage directories with subject dirs
    for stage in ["01_data", "02_processed"]:
        for sub in ["sub-001A", "sub-002B", "sub-003C"]:
            (tmp_path / stage / sub).mkdir(parents=True)

    return tmp_path
