"""Rich input — prompt-toolkit session with history and auto-suggest."""

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.formatted_text import HTML

if TYPE_CHECKING:
    from agent_cli.config import CLIConfig


def _build_bindings() -> KeyBindings:
    """Key bindings: Enter submits, Escape+Enter inserts newline."""
    kb = KeyBindings()

    @kb.add(Keys.Escape, Keys.Enter)
    def _newline(event):
        event.current_buffer.insert_text("\n")

    return kb


def create_session(config: CLIConfig) -> PromptSession:
    """Create a prompt-toolkit PromptSession with history and auto-suggest.

    - FileHistory persists across sessions at ``~/.agent/history``
    - Enter submits; Escape+Enter (or Meta+Enter) inserts a newline
    - Fish-style inline suggestions from history
    - vi_mode toggled from config
    """
    history = FileHistory(str(config.history_file))
    bindings = _build_bindings()

    return PromptSession(
        message=HTML(
            '<style fg="ansibrightblack">───</style>\n'
            '<b><style fg="ansicyan">❯</style></b> '
        ),
        history=history,
        auto_suggest=AutoSuggestFromHistory(),
        key_bindings=bindings,
        vi_mode=config.vi_mode,
        multiline=False,
        enable_open_in_editor=False,
    )
