"""
DataLad command interface for runcmd.

This allows calling the tool as:
  datalad runcmd <script> [args ...]

Requires DataLad to be installed.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from datalad.interface.base import Interface, build_doc
    from datalad.interface.results import get_status_dict
    from datalad.interface.utils import default_result_renderer, eval_results
    from datalad.support.constraints import EnsureNone, EnsureStr
    from datalad.support.param import Parameter
    from datalad.ui import ui

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
        def custom_result_renderer(res, **kwargs):
            if res["action"] != "runcmd":
                default_result_renderer(res)
            elif res["status"] == "ok":
                ui.message(res["message"])
            else:
                default_result_renderer(res)

        @staticmethod
        @eval_results
        def __call__(
            script,
            args=None,
            dataset=None,
        ):
            from datalad.distribution.dataset import require_dataset

            from datalad_runcmd.cli import resolve_command
            from datalad_runcmd.resolve import ResolutionError

            ds = require_dataset(
                dataset,
                check_installed=True,
                purpose="resolve runcmd",
            )

            try:
                result = resolve_command(
                    script,
                    args or [],
                    cwd=Path(ds.path),
                )
            except (FileNotFoundError, ValueError, ResolutionError) as exc:
                yield get_status_dict(
                    action="runcmd",
                    ds=ds,
                    status="error",
                    message=str(exc),
                    type="dataset",
                )
                return

            # Emit warnings
            for w in result.warnings:
                logger.warning("%s", w.message)

            if len(result.all_commands) > 1:
                from datalad_runcmd.cli import _format_multi_command

                yield get_status_dict(
                    action="runcmd",
                    ds=ds,
                    status="ok",
                    message=_format_multi_command(result.all_commands),
                    type="dataset",
                )
            else:
                yield get_status_dict(
                    action="runcmd",
                    ds=ds,
                    status="ok",
                    message=result.command,
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
