from typing import Any, TypedDict


class Asset(TypedDict):
    """Base class for trade assets."""
    players: list[dict[str, Any]]
    picks: list[dict[str, Any]]
