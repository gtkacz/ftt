from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.query import QuerySet

from core.models import Team, User


class Trade(models.Model):
	"""A trade between teams involving various assets."""

	sender = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="trades_created")
	participants = models.ManyToManyField("core.Team", related_name="trades")
	parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="succeeded_by")

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:  # noqa: D106
		ordering = ("created_at", "updated_at")
		indexes = (
			models.Index(fields=["sender"]),
			models.Index(fields=["parent"]),
		)

	def __str__(self) -> str:
		return f"Trade #{self.pk} by {self.sender}"

	@property
	def is_latest(self) -> bool:
		"""Check if the trade is still active (not succeeded by another trade)."""
		return not self.succeeded_by.exists()

	@property
	def status(self) -> int:
		"""
		Determine the current status of the trade.

		Raises:
			ValidationError: If the status is unknown.

		Returns:
			int: 0 for open, -1 for closed, 1 for done.
		"""
		statuses = self.statuses.all()

		for status in statuses:
			if status.current_status != 0:
				return status.current_status

		raise ValidationError("Unknown status")

	@property
	def participant_statuses(self) -> dict[int, str]:
		"""
		Get the current status for each participant in the trade.

		Raises:
			ValidationError: If any status is unknown.

		Returns:
			dict[int, str]: A mapping of participant team IDs to their status codes.
		"""
		status_dict = {}
		statuses = self.statuses.all()

		for participant in self.participants.all():
			status_dict[participant.id] = statuses.filter(actioned_by=participant).order_by("-created_at")[:1]

		if any(participant not in status_dict for participant in self.participants.all()):
			raise ValidationError("Unknown status for one or more participants")

		return status_dict

	@property
	def commissioner_statuses(self) -> dict[int, str]:
		"""
		Get the current status for each commissioner in the trade.

		Raises:
			ValidationError: If any status is unknown.

		Returns:
			dict[int, str]: A mapping of commissioner team IDs to their status codes.
		"""
		status_dict = {}
		statuses = self.statuses.all()

		for commissioner in self.get_commissioners():
			status_dict[commissioner.id] = statuses.filter(actioned_by=commissioner).order_by("-created_at")[:1]

		if any(commissioner not in status_dict for commissioner in self.sender.commissioners.all()):
			raise ValidationError("Unknown status for one or more commissioners")

		return status_dict

	@property
	def is_accepted(self) -> bool:
		"""
		Check if all participants have accepted the trade.

		Returns:
			bool: True if all participants have accepted, False otherwise.
		"""
		statuses = self.statuses.all()
		accepted_status = "accepted"

		for participant in self.participants.all():
			participant_statuses = statuses.filter(actioned_by=participant).order_by("-created_at")

			if not participant_statuses.exists() or participant_statuses.first().status != accepted_status:
				return False

		return True

	@property
	def is_rejected(self) -> bool:
		"""
		Check if any participant has rejected the trade.

		Returns:
			bool: True if any participant has rejected, False otherwise.
		"""
		statuses = self.statuses.all()
		rejected_status = "rejected"

		for participant in self.participants.all():
			participant_statuses = statuses.filter(actioned_by=participant).order_by("-created_at")

			if participant_statuses.exists() and participant_statuses.first().status == rejected_status:
				return True

		return False

	@property
	def is_approved(self) -> bool:
		"""
		Check if the trade has been approved.
		A trade is approved if it's approved by at least one admin or by the majority of commissioners.

		Returns:
			bool: True if the trade is approved, False otherwise.
		"""
		statuses = self.statuses.all()
		approved_status = "approved"

		# Check for admin approval
		for admin in self.get_admins():
			admin_statuses = statuses.filter(actioned_by=admin).order_by("-created_at")

			if admin_statuses.exists() and admin_statuses.first().status == approved_status:
				return True

		# Check for commissioner approval
		approvals = 0
		total_commissioners = self.get_commissioners().count()

		for commissioner in self.get_commissioners():
			commissioner_statuses = statuses.filter(actioned_by=commissioner).order_by("-created_at")

			if commissioner_statuses.exists() and commissioner_statuses.first().status == approved_status:
				approvals += 1

		return approvals > total_commissioners / 2

	@staticmethod
	def get_commissioners() -> QuerySet[Team]:
		"""
		Get all commissioners associated with the league.

		Returns:
			QuerySet: A queryset of commissioner teams.
		"""
		return Team.objects.filter(owner__in=User.objects.filter(is_staff=True))

	@staticmethod
	def get_admins() -> QuerySet[Team]:
		"""
		Get all admins associated with the league.

		Returns:
			QuerySet: A queryset of commissioner teams.
		"""
		return Team.objects.filter(owner__in=User.objects.filter(is_superuser=True))
