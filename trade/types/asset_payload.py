from typing import TypedDict, NotRequired

from trade.enums.protections import PickProtections


class PickPayloadDict(TypedDict):
	"""Payload for a draft pick asset in a trade."""

	id: int
	protection: PickProtections
	metadata: NotRequired[dict]


class AssetPayloadDict(TypedDict):
	"""Payload for assets in a trade."""

	players: list[int]
	picks: list[PickPayloadDict]


class AssetPayload(TypedDict):
	"""Payload for trade asset creation."""

	receiver: int
	assets: AssetPayloadDict
