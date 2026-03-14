"""Extract and resolve datalad run commands from script docstrings."""

__version__ = "0.1.0"

# DataLad extension registration
# This tuple tells datalad where to find the command suite:
#   (description, list of (module_path, class_name, command_name))
command_suite = (
    "Extract and resolve datalad run commands from script docstrings",
    [
        (
            "datalad_runcmd.dl_command",
            "RunCmd",
            "runcmd",
        ),
    ],
)
