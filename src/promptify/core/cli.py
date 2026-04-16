"""
COMMAND LINE INTERFACE PARSING AND DEFINITION ARCHITECTURE.
"""

import argparse
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class CLIConfig:
    """
    CONFIGURATION PARAMETERS FOR RUNNING PROMPTIFY PROGRAMMATICALLY OR VIA CLI.
    THIS DOCSTRING DYNAMICALLY POPULATES THE CLI HELP COMMAND.

    Args:
        case (str): Choose case by their name defined in the config.json. On duplicate, errors out and notifies that only normal mode supports duplicates, and if they want to use CLI, then the user needs to adjust their cases to not contain duplicate names. Accepts case name as a string. No default.
        path (str): Target project path that will be scanned. Accepts valid (existing) paths. No default.
        mode (str): Working mode. Accepts either 's', 'simple', 'l', 'legacy', 'o', 'old' vs 'i', 'interactive', 'a', 'advanced', 'e', 'editor'. Default is interactive mode.
    """

    case: Optional[str] = None
    path: Optional[str] = None
    mode: Optional[str] = None


def extract_help_from_docstring(cls: type) -> dict[str, str]:
    """DYNAMICALLY PULLS DOCSTRINGS FROM THE SOURCE CODE TO ENSURE SYNCHRONIZATION."""
    doc = cls.__doc__ or ""
    helps = {}
    for line in doc.splitlines():
        # CAPTURES DEFINITIONS LIKE ->  `   CASE (STR): DESCRIPTION...`
        match = re.match(r"\s*([a-zA-Z0-9_]+)\s*\([^)]+\)\s*:\s*(.*)", line)
        if match:
            helps[match.group(1)] = match.group(2).strip()
    return helps


def parse_cli_args(args: list[str] | None = None) -> CLIConfig:
    """PARSES SYS.ARGV USING DYNAMICALLY INJECTED DOCSTRINGS."""
    helps = extract_help_from_docstring(CLIConfig)

    parser = argparse.ArgumentParser(
        prog="promptify",
        description="Bridge the gap between your local source code and LLMs.",
        add_help=False,  # CUSTOMIZING TO MAP TO `-H` CLEANLY
    )

    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="Display help message with commands and arguments then exits.",
    )

    parser.add_argument(
        "-c", "--case", type=str, help=helps.get("case", "Choose case by name.")
    )

    parser.add_argument(
        "-p", "--path", type=str, help=helps.get("path", "Target project path.")
    )

    parser.add_argument(
        "-m", "--mode", type=str, help=helps.get("mode", "Working mode.")
    )

    parsed, _ = parser.parse_known_args(args)

    return CLIConfig(case=parsed.case, path=parsed.path, mode=parsed.mode)
