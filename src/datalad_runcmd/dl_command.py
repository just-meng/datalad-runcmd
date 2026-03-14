"""
DataLad command interface for runcmd.

This allows calling the tool as:
  datalad runcmd <script> [args ...]

Requires DataLad to be installed.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from datalad.interface.base import Interface, build_doc
    from datalad.interface.results import get_status_dict
    from datalad.support.constraints import EnsureNone, EnsureStr
    from datalad.support.param import Parameter

    @build_doc
    class RunCmd(Interface):
        """Extract and resolve datalad run commands from script docstrings.

        Given a script name and positional arguments, this command finds the
        script in the configured directories, extracts the ``datalad run``
        command from its docstring, resolves ``{placeholder}`` tokens using
        ``.datalad/runcmd.toml``, and prints the resolved command.

        Examples::

            datalad runcmd run_suite2p.py 01
            datalad runcmd run_fissa.py ket pre
        """

        _params_ = dict(
            script=Parameter(
                args=("script",),
                doc="Script filename (e.g. run_fissa.py)",
                constraints=EnsureStr(),
            ),
            args=Parameter(
                args=("args",),
                doc="Positional arguments mapped to placeholders in occurrence order",
                nargs="*",
            ),
            dataset=Parameter(
                args=("-d", "--dataset"),
                doc="Path to the dataset root (default: current directory)",
                constraints=EnsureStr() | EnsureNone(),
            ),
        )

        @staticmethod
        def __call__(
            script,
            args=None,
            dataset=None,
        ):
            from pathlib import Path

            from datalad.distribution.dataset import require_dataset

            from datalad_runcmd.cli import _find_placeholders, main

            ds = require_dataset(
                dataset,
                check_installed=True,
                purpose="resolve runcmd",
            )

            # Delegate to the CLI main with the resolved dataset path as cwd
            import os
            import sys
            from io import StringIO

            argv = [script] + (args or [])

            # Capture stdout to get the resolved command
            old_cwd = os.getcwd()
            old_stdout = sys.stdout
            buf = StringIO()
            try:
                os.chdir(ds.path)
                sys.stdout = buf
                main(argv)
                sys.stdout = old_stdout
                output = buf.getvalue().strip()
            except SystemExit as exc:
                sys.stdout = old_stdout
                msg = buf.getvalue().strip() or str(exc)
                yield get_status_dict(
                    action="runcmd",
                    ds=ds,
                    status="error",
                    message=msg,
                    type="dataset",
                )
                return
            finally:
                os.chdir(old_cwd)

            # Split output: last non-warning line is the command,
            # warning lines go to stderr
            lines = output.split("\n")
            cmd_lines = [l for l in lines if not l.startswith("Warning:")]
            warnings = [l for l in lines if l.startswith("Warning:")]

            for w in warnings:
                logger.warning(w)

            yield get_status_dict(
                action="runcmd",
                ds=ds,
                status="ok",
                message="\n".join(cmd_lines),
                type="dataset",
            )

except ImportError:
    logger.debug(
        "DataLad not available; datalad runcmd command not registered"
    )

    class RunCmd:
        """Placeholder when DataLad is not installed."""

        def __call__(self, *args, **kwargs):
            raise RuntimeError(
                "DataLad is not installed. Use the standalone CLI: runcmd"
            )
