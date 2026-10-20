"""Goal suggestion wording (POST /goal-suggestions). `router` is imported lazily so the pure modules work without FastAPI."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "router":
        from .api import router

        return router
    raise AttributeError(name)


__all__ = ["router"]
