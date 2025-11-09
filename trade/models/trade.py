from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.query import QuerySet
from django.db.transaction import atomic

from core.models import Team, User
from ftt.common.util import django_obj_to_dict
from ftt.settings import LEAGUE_SETTINGS
from trade.models.trade_status import TradeStatus


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

	def save(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003, D102
		if hasattr(self, "pk") and self.pk and self.is_approved and self.is_latest:
			for asset in self.assets.all():
				asset.transfer_asset()

		super().save(*args, **kwargs)

		self.create_trade_status_if_needed()

	def validate_compliance(self) -> None:
		"""
		Validate the trade.

		Raises:
			ValidationError: If the trade is invalid.
		"""
		# Ensure at least two participants
		if self.participants.count() < 2:
			raise ValidationError("A trade must involve at least two participants.")

		# Check every team is sending and receiving at least one asset
		for participant in self.participants.all():
			sent_assets = self.assets.filter(sender=participant)
			received_assets = self.assets.filter(receiver=participant)

			if not sent_assets.exists():
				raise ValidationError(f"Participant {participant} is not sending any assets.")

			if not received_assets.exists():
				raise ValidationError(f"Participant {participant} is not receiving any assets.")

		# Check after the trade every team is in compliance with league rules
		for participant in self.participants.all():
			if (
				participant.total_players() > LEAGUE_SETTINGS.MAX_PLAYER_CAP
				or participant.total_players() < LEAGUE_SETTINGS.MIN_PLAYER_CAP
				or participant.total_salary() > LEAGUE_SETTINGS.SALARY_CAP
			):
				raise ValidationError(f"Participant {participant} would be out of compliance after this trade.")

	@atomic
	def create_trade_status_if_needed(self) -> None:
		"""
		Create trade statuses for participants.
		"""
		if not self.parent:
			TradeStatus.objects.bulk_create(
				[
					TradeStatus(trade=self, actioned_by=participant, status="sent")
					for participant in self.participants.all()
				],
			)

		TradeStatus.objects.bulk_create(
			[
				TradeStatus(trade=self, actioned_by=commissioner, status="pending")
				for commissioner in self.get_commissioners()
			],
		)

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
			if statuses.filter(actioned_by=participant).order_by("-created_at").exists():
				status_dict[participant.id] = django_obj_to_dict(
					statuses.filter(actioned_by=participant).order_by("-created_at").first(),
				)

		if any(participant.id not in status_dict for participant in self.participants.all()):
			raise ValidationError(f"Unknown status for one or more participants: {status_dict}")

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
			if statuses.filter(actioned_by=commissioner).exists():
				status_dict[commissioner.id] = django_obj_to_dict(
					statuses.filter(actioned_by=commissioner).order_by("-created_at").first(),
				)

		if any(commissioner.id not in status_dict for commissioner in self.get_commissioners()):
			raise ValidationError(f"Unknown status for one or more commissioners: {status_dict}")

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

	def get_commissioners(self) -> QuerySet[Team]:
		"""
		Get all commissioners associated with the league.

		Returns:
			QuerySet: A queryset of commissioner teams.
		"""
		return (
			Team.objects.filter(owner__in=User.objects.filter(is_staff=True))
			if self.is_accepted
			else Team.objects.none()
		)

	def get_admins(self) -> QuerySet[Team]:
		"""
		Get all admins associated with the league.

		Returns:
			QuerySet: A queryset of commissioner teams.
		"""
		return (
			Team.objects.filter(owner__in=User.objects.filter(is_superuser=True))
			if self.is_accepted
			else Team.objects.none()
		)
