from enum import StrEnum


class TradeStatuses(StrEnum):
	"""The status of a trade."""

	SENT = "sent"
	COUNTEROFFER = "counteroffer"
	REJECTED = "rejected"
	ACCEPTED = "accepted"
	PENDING = "pending"
	VETOED = "vetoed"
	APPROVED = "approved"
