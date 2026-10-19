"""Fraud consultant; lazy router import keeps pure contracts independent."""
from typing import Any


def __getattr__(name: str) -> Any:
    if name == "router":
        from .api import router
        return router
    raise AttributeError(name)


__all__ = ["router"]
