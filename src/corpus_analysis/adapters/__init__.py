"""Adapter registry. One name per vendor format."""

from __future__ import annotations

from . import (
    chatgpt,
    claude_code,
    claude_export,
    codex,
    copilot_cli,
    cursor,
    opencode,
    vscode_chat,
)
from .base import Adapter, SchemaDrift, SessionRef

REGISTRY: dict[str, object] = {
    chatgpt.name: chatgpt,
    claude_code.name: claude_code,
    claude_export.name: claude_export,
    codex.name: codex,
    copilot_cli.name: copilot_cli,
    opencode.name: opencode,
    cursor.name: cursor,
    vscode_chat.name: vscode_chat,
}


def get(name: str):
    try:
        return REGISTRY[name]
    except KeyError:
        raise SystemExit(
            f"unknown adapter {name!r}; available: {', '.join(sorted(REGISTRY))}"
        ) from None


def names() -> list[str]:
    return sorted(REGISTRY)


__all__ = ["Adapter", "SchemaDrift", "SessionRef", "REGISTRY", "get", "names"]
