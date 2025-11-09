from django.core.exceptions import ValidationError
from django.db import models


class TradeStatus(models.Model):
	"""The status of a trade."""

	TRADE_STATUS_CHOICES = (
		("draft", "DRAFT"),
		("sent", "SENT"),
		("rejected", "REJECTED"),
		("counteroffer", "COUNTEROFFER"),
		("accepted", "ACCEPTED"),
		("pending", "PENDING"),
		("vetoed", "VETOED"),
		("approved", "APPROVED"),
	)

	trade = models.ForeignKey("trade.Trade", on_delete=models.CASCADE, related_name="statuses")
	status = models.CharField(max_length=20, choices=TRADE_STATUS_CHOICES)
	actioned_by = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="trade_actions")

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:  # noqa: D106
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
			self.TRADE_STATUS_CHOICES[0][0],
			self.TRADE_STATUS_CHOICES[1][0],
			self.TRADE_STATUS_CHOICES[2][0],
			self.TRADE_STATUS_CHOICES[3][0],
			self.TRADE_STATUS_CHOICES[4][0],
		}

		commissioner_statuses = {
			self.TRADE_STATUS_CHOICES[5][0],
			self.TRADE_STATUS_CHOICES[6][0],
		}

		if (self.actioned_by.owner.is_staff or self.actioned_by.owner.is_superuser) and self.status in user_statuses:
			raise ValidationError("Commissioners cannot use user statuses.")

		if (
			not (self.actioned_by.owner.is_staff or self.actioned_by.owner.is_superuser)
			and self.status in commissioner_statuses
		):
			raise ValidationError("Users cannot use commissioner statuses.")

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
			self.TRADE_STATUS_CHOICES[0][0],
			self.TRADE_STATUS_CHOICES[1][0],
			self.TRADE_STATUS_CHOICES[3][0],
			self.TRADE_STATUS_CHOICES[4][0],
		}
		is_closed = {self.TRADE_STATUS_CHOICES[2][0], self.TRADE_STATUS_CHOICES[5][0]}
		is_done = {self.TRADE_STATUS_CHOICES[6][0]}

		if self.status in is_open:
			return 0

		if self.status in is_closed:
			return -1

		if self.status in is_done:
			return 1

		raise ValidationError("Unknown status")
