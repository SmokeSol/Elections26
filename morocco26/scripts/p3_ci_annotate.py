#!/usr/bin/env python3
from __future__ import annotations

"""Make a CI failure readable without a signed-in session.

Actions logs and artifacts both require authentication, so a failing build in
this repository has been reduced to an opaque exit code more than once. Check-run
annotations are public, and a `::error::` workflow command becomes one.

Wrapping a script's entry point with `run_guarded` therefore turns any
unhandled exception into a fact anyone can read through the API, instead of
"Process completed with exit code 1".
"""

import os
import sys
import traceback
from typing import Callable, Sequence

MAX_MESSAGE = 3500


def _escape(value: str) -> str:
    """Workflow-command escaping: newlines and delimiters must be encoded."""
    return (
        str(value)
        .replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def in_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def emit(level: str, title: str, message: str) -> None:
    text = message if len(message) <= MAX_MESSAGE else message[:MAX_MESSAGE] + " [truncated]"
    if in_actions():
        print(f"::{level} title={_escape(title)}::{_escape(text)}", flush=True)
    print(f"[{level}] {title}: {text}", file=sys.stderr, flush=True)


def emit_error(title: str, message: str) -> None:
    emit("error", title, message)


def emit_notice(title: str, message: str) -> None:
    emit("notice", title, message)


def run_guarded(main: Callable[[Sequence[str] | None], int], argv: Sequence[str] | None = None) -> int:
    """Run `main`, turning any escape into a public annotation."""
    try:
        return int(main(argv))
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code:
            emit_error("exited", f"{sys.argv[0]} exited with code {code}")
        return code
    except BaseException as exc:  # noqa: BLE001 - the point is to report everything
        frames = traceback.format_exception(type(exc), exc, exc.__traceback__)
        emit_error(
            f"{type(exc).__name__} in {os.path.basename(sys.argv[0])}",
            "".join(frames[-6:]).strip(),
        )
        return 1
