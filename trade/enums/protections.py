from enum import StrEnum


class PickProtections(StrEnum):
	"""Enumeration of pick protection types."""
	UNPROTECTED = "unprotected"
	TOP_X = "top_x"
	SWAP_BEST = "swap_best"
	SWAP_WORST = "swap_worst"
