"""Shared prompt-toolkit dialogs for menu-level questions"""

from __future__ import annotations

from prompt_toolkit.shortcuts import yes_no_dialog


async def ask_yes_no_modal(*, title: str, text: str) -> bool:
    """Show a centered yes/no dialog and return the chosen answer"""
    result = await yes_no_dialog(title=title, text=text).run_async()
    return bool(result)
