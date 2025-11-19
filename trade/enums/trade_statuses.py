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

	@classmethod
	def get_staff_only_statuses(cls) -> list["TradeStatuses"]:
		"""
		Get a list of statuses that only staff members can set.

		Returns:
			list[TradeStatuses]: A list of staff-only trade statuses.
		"""
		return [cls.PENDING.value, cls.VETOED.value, cls.APPROVED.value]
