from django.db import models


class Trade(models.Model):
	"""Model representing a trade between teams in a fantasy league."""

	teams = models.ManyToManyField(
		"Team",
		related_name="trades",
		help_text="Teams involved in the trade",
	)
	messages = models.JSONField(
		default=dict,
		blank=True,
		null=True,
		help_text="Messages accompanying the trade offer",
	)
	players = models.ManyToManyField("Player", related_name="trades_from", blank=True)
	picks = models.ManyToManyField("draft.Pick", related_name="trades_from", blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	approved_at = models.DateTimeField(
		blank=True,
		null=True,
		help_text="Timestamp when the trade was approved",
	)
	approved_by = models.JSONField(
		default=list,
		blank=True,
		null=True,
		help_text="Commissioners who approved the trade",
	)
	status = models.CharField(
		max_length=20,
		choices=[
			("pending", "Pending"),
			("accepted", "Accepted"),
			("rejected", "Rejected"),
			("cancelled", "Cancelled"),
			("waiting_approval", "Waiting for Approval"),
		],
		default="pending",
		help_text="Status of the trade",
	)

	def __str__(self) -> str:
		return f"Trade {self.id} - Status: {self.status}"  # pyright: ignore[reportAttributeAccessIssue]
