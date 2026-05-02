"""Overlay and focus management mixin for the interactive editor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from ...shared.editor_state import EditorViewState, FocusTarget, OverlayName
from ._imports import Buffer, SelectionState, get_app

if TYPE_CHECKING:

    class _EditorOverlayHost:
        _overlay_visibility: dict[OverlayName, bool]
        _overlay_restore_focus: dict[OverlayName, FocusTarget]
        _overlay_suspended: dict[OverlayName, OverlayName]
        _overlay_view_state: dict[OverlayName, EditorViewState | None]
        search_visible: bool
        replace_visible: bool
        jump_visible: bool
        issue_mode_active: bool
        _help_search_anchor: int
        _help_issue_anchor: int
        result: str | None
        buffer: Buffer
        search_buffer: Buffer
        replace_buffer: Buffer
        jump_buffer: Buffer
        help_window: Any
        err_window: Any
        quit_window: Any
        main_window: Any
        quit_buffer: Buffer

        def _set_help_cursor(self, position: int) -> None: ...
        def note_user_activity(self) -> None: ...
else:

    class _EditorOverlayHost:
        pass


class EditorOverlayMixin(_EditorOverlayHost):
    """Provide shared overlay visibility, focus, and restore behavior."""

    def _copy_selection_state(
        self, selection_state: SelectionState | None
    ) -> SelectionState | None:
        """Clone a selection snapshot so help overlays can restore it cleanly."""
        if selection_state is None:
            return None
        return SelectionState(
            original_cursor_position=selection_state.original_cursor_position,
            type=selection_state.type,
        )

    def _restore_selection_state(
        self, buffer: Buffer, selection_state: SelectionState | None
    ) -> None:
        """Reapply a saved selection snapshot to a target buffer."""
        buffer.selection_state = self._copy_selection_state(selection_state)

    @property
    def help_visible(self) -> bool:
        """Expose help visibility while storing overlay state centrally."""
        return self._overlay_visibility["help"]

    @help_visible.setter
    def help_visible(self, value: bool) -> None:
        self._overlay_visibility["help"] = value

    @property
    def err_visible(self) -> bool:
        """Expose error visibility while storing overlay state centrally."""
        return self._overlay_visibility["error"]

    @err_visible.setter
    def err_visible(self, value: bool) -> None:
        self._overlay_visibility["error"] = value

    @property
    def quit_visible(self) -> bool:
        """Expose quit visibility while storing overlay state centrally."""
        return self._overlay_visibility["quit"]

    @quit_visible.setter
    def quit_visible(self, value: bool) -> None:
        self._overlay_visibility["quit"] = value

    def _set_overlay_visible(self, overlay: OverlayName, visible: bool) -> None:
        """Update overlay visibility through the shared registry."""
        if overlay == "none":
            return
        self._overlay_visibility[overlay] = visible

    def _get_visible_overlay(self) -> OverlayName:
        """Return the currently visible modal overlay, if any."""
        for overlay in ("help", "quit", "error"):
            if self._overlay_visibility[cast(OverlayName, overlay)]:
                return cast(OverlayName, overlay)
        return "none"

    def _get_focus_target(self) -> FocusTarget:
        """Describe which editor surface currently owns user attention."""
        overlay = self._get_visible_overlay()
        if overlay != "none":
            return cast(FocusTarget, overlay)
        if self.jump_visible:
            return "jump"
        if self.replace_visible:
            return "replace"
        if self.search_visible:
            return "search"
        return "main"

    def _capture_view_state(self) -> EditorViewState:
        """Snapshot editor input cursors plus selections for later restore."""
        return EditorViewState(
            focus=self._get_focus_target(),
            main_cursor=self.buffer.cursor_position,
            search_cursor=self.search_buffer.cursor_position,
            replace_cursor=self.replace_buffer.cursor_position,
            jump_cursor=self.jump_buffer.cursor_position,
            main_selection=self._copy_selection_state(self.buffer.selection_state),
            search_selection=self._copy_selection_state(
                self.search_buffer.selection_state
            ),
            replace_selection=self._copy_selection_state(
                self.replace_buffer.selection_state
            ),
            jump_selection=self._copy_selection_state(self.jump_buffer.selection_state),
        )

    def _restore_view_state(self, state: EditorViewState) -> None:
        """Restore editor input cursors plus selections from a snapshot."""
        self.buffer.cursor_position = state.main_cursor
        self.search_buffer.cursor_position = state.search_cursor
        self.replace_buffer.cursor_position = state.replace_cursor
        self.jump_buffer.cursor_position = state.jump_cursor
        self._restore_selection_state(self.buffer, state.main_selection)
        self._restore_selection_state(self.search_buffer, state.search_selection)
        self._restore_selection_state(self.replace_buffer, state.replace_selection)
        self._restore_selection_state(self.jump_buffer, state.jump_selection)

    def _focus_target(self, target: FocusTarget) -> None:
        """Route focus changes through one place for all editor surfaces."""
        if target == "search" and self.search_visible:
            self._focus(self.search_buffer)
        elif target == "replace" and self.search_visible and self.replace_visible:
            self._focus(self.replace_buffer)
        elif target == "jump" and self.jump_visible:
            self._focus(self.jump_buffer)
        elif target == "help" and self.help_visible:
            self._focus(self.help_window)
        elif target == "error" and self.err_visible:
            self._focus(self.err_window)
        elif target == "quit" and self.quit_visible:
            self._focus(self.quit_window)
        else:
            self._focus(self.main_window)

    def _show_overlay(
        self,
        overlay: OverlayName,
        *,
        restore_focus: FocusTarget | None = None,
        preserve_view: bool = False,
    ) -> OverlayName:
        """Show one overlay, suspending any currently visible overlay beneath it."""
        current_focus = restore_focus or self._get_focus_target()
        suspended = self._get_visible_overlay()
        if suspended != "none" and suspended != overlay:
            self._set_overlay_visible(suspended, False)
        elif suspended == overlay:
            suspended = self._overlay_suspended[overlay]

        self._overlay_suspended[overlay] = suspended
        self._overlay_restore_focus[overlay] = current_focus
        self._overlay_view_state[overlay] = (
            self._capture_view_state() if preserve_view else None
        )
        self._set_overlay_visible(overlay, True)
        return suspended

    def _hide_overlay(
        self, overlay: OverlayName, *, restore_view: bool = False
    ) -> None:
        """Hide one overlay and resume the previously suspended overlay or focus target."""
        suspended = self._overlay_suspended[overlay]
        restore_focus = self._overlay_restore_focus[overlay]
        view_state = self._overlay_view_state[overlay]

        self._set_overlay_visible(overlay, False)
        self._overlay_suspended[overlay] = "none"
        self._overlay_view_state[overlay] = None

        if restore_view and view_state is not None:
            self._restore_view_state(view_state)

        if suspended != "none":
            self._set_overlay_visible(suspended, True)
            self._focus_target(cast(FocusTarget, suspended))
        else:
            self._focus_target(restore_focus)

    def _focus(self, target) -> None:
        """Focus a target if an application is active."""
        try:
            get_app().layout.focus(target)
        except Exception:
            pass

    def invalidate(self) -> None:
        """Request a redraw when an application is active."""
        try:
            app = get_app()
        except Exception:
            return
        if app:
            app.invalidate()

    def open_help(self) -> None:
        """Show the help overlay and focus it."""
        self._show_overlay("help", preserve_view=True)
        if self.search_visible and self._help_search_anchor >= 0:
            self._set_help_cursor(self._help_search_anchor)
        elif self.issue_mode_active and self._help_issue_anchor >= 0:
            self._set_help_cursor(self._help_issue_anchor)
        else:
            self._set_help_cursor(0)
        self._focus_target("help")
        self.invalidate()

    def close_help(self) -> None:
        """Hide the help overlay and return focus to the active edit target."""
        self._hide_overlay("help", restore_view=True)
        self.invalidate()

    def toggle_help(self) -> None:
        """Toggle help visibility without losing the active search context."""
        if self.help_visible:
            self.close_help()
        else:
            self.open_help()

    def open_quit_confirm(self) -> None:
        """Show a confirmation modal before aborting the editor session."""
        self.note_user_activity()
        self._show_overlay("quit")
        self.quit_buffer.cursor_position = 0
        self._focus_target("quit")
        self.invalidate()

    def close_quit_confirm(self) -> None:
        """Dismiss the quit modal and restore focus to the previous target."""
        self._hide_overlay("quit")
        self.invalidate()

    def confirm_quit(self) -> None:
        """Abort the current editor session without saving."""
        self._set_overlay_visible("quit", False)
        self.result = None
        self.invalidate()
