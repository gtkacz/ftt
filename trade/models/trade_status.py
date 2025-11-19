from enum import Enum

from django.core.exceptions import ValidationError
from django.db import models


class TradeStatus(models.Model):
	"""The status of a trade."""

	class TradeStatusChoices(Enum):
		"""Enumeration of possible trade statuses."""

		SENT = ("sent", "SENT")
		REJECTED = ("rejected", "REJECTED")
		ACCEPTED = ("accepted", "ACCEPTED")
		PENDING = ("pending", "PENDING")
		VETOED = ("vetoed", "VETOED")
		APPROVED = ("approved", "APPROVED")

	trade = models.ForeignKey("trade.Trade", on_delete=models.CASCADE, related_name="statuses")
	status = models.CharField(max_length=20, choices=TradeStatusChoices._hashable_values_)
	actioned_by = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="trade_actions")

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ("created_at", "updated_at")
		unique_together = (("trade", "actioned_by", "status"),)
		indexes = (
			models.Index(fields=["trade"]),
			models.Index(fields=["trade", "actioned_by"]),
			models.Index(fields=["status", "actioned_by"]),
		)

	def __str__(self) -> str:
		return f"Status ({self.status}) for trade {self.trade.id} by {self.actioned_by.name}"

	def save(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
		"""
		Check if users aren't using commissioner statuses and that commissioners aren't using user statuses.

		Raises:
			ValidationError: If a user or commissioner uses an invalid status.
			ValidationError: If the status is unknown.
		"""
		user_statuses = {
			self.TradeStatusChoices.SENT.value[0],
			self.TradeStatusChoices.REJECTED.value[0],
			self.TradeStatusChoices.ACCEPTED.value[0],
		}

		commissioner_statuses = {
			self.TradeStatusChoices.PENDING.value[0],
			self.TradeStatusChoices.VETOED.value[0],
			self.TradeStatusChoices.APPROVED.value[0],
		}

		if self.actioned_by == self.trade.sender and self.status in list(user_statuses)[1:]:
			raise ValidationError(f"You cannot perform {self.status}.")

		if (
			(self.actioned_by.owner.is_staff or self.actioned_by.owner.is_superuser)
			and self.actioned_by not in self.trade.participants.all()
			and self.status in user_statuses
		):
			raise ValidationError("Commissioners cannot use user statuses.")

		if (
			not (self.actioned_by.owner.is_staff or self.actioned_by.owner.is_superuser)
			and self.status in commissioner_statuses
		):
			raise ValidationError("Users cannot use commissioner statuses.")

		print(f"{self.__dict__}\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n")
		super().save(*args, **kwargs)

	@property
	def current_status(self) -> int:
		"""
		Translates the trade status into an integer code.

		Raises:
			ValidationError: If the status is unknown.

		Returns:
			int: 0 for open, -1 for closed, 1 for done.
		"""
		is_open = {
			self.TradeStatusChoices[0][0],
			self.TradeStatusChoices[1][0],
			self.TradeStatusChoices[3][0],
			self.TradeStatusChoices[4][0],
		}
		is_closed = {self.TradeStatusChoices[2][0], self.TradeStatusChoices[5][0]}
		is_done = {self.TradeStatusChoices[6][0]}

		if self.status in is_open:
			return 0

		if self.status in is_closed:
			return -1

		if self.status in is_done:
			return 1

		raise ValidationError("Unknown status")
