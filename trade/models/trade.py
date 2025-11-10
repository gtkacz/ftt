from collections import defaultdict
from typing import Optional

from box import Box
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.query import QuerySet
from django.db.transaction import atomic

from core.models import Notification, Team, User
from ftt.common.util import django_obj_to_dict
from ftt.settings import LEAGUE_SETTINGS
from trade.enums.trade_statuses import TradeStatuses
from trade.models.trade_status import TradeStatus
from trade.types.timeline import TimelineEntry


class Trade(models.Model):
	"""A trade between teams involving various assets."""

	sender = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="trades_created")
	participants = models.ManyToManyField("core.Team", related_name="trades")
	parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="succeeded_by")
	done = models.BooleanField(default=False)

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
		if hasattr(self, "pk") and self.pk:
			self.handle_changes()

		super().save(*args, **kwargs)

		self.handle_changes()

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
	def handle_changes(self) -> None:
		"""
		Handle changes to the trade.
		"""
		# If the trade is vetoed, mark it as done
		if self.is_vetoed:
			self.done = True

			Notification.objects.bulk_create(
				[
					Notification(
						user=participant.owner,
						message="A trade you are involved in has been vetoed by the commissioners.",
						level="warning",
						redirect_to=f"/trades/{self.pk}/",
					)
					for participant in self.participants.all()
				],
			)

			return

		# If the trade is finalized, transfer all assets
		if self.is_approved:
			for asset in self.assets.all():
				asset.transfer_asset()

			self.done = True

			Notification.objects.bulk_create(
				[
					Notification(
						user=participant.owner,
						message="A trade you are involved in has been approved and assets have been transferred.",
						level="success",
						redirect_to=f"/trades/{self.pk}/",
					)
					for participant in self.participants.all()
				],
			)

			# Warn everyone else in the league about the completed trade
			Notification.objects.bulk_create(
				[
					Notification(
						user=team.owner,
						message="A trade has been completed in the league.",
						level="info",
						redirect_to=f"/trades/{self.pk}/",
					)
					for team in Team.objects.exclude(id__in=self.participants.all().values_list("id", flat=True))
				],
			)

			return

		# When the trade is sent, create trade statuses for participants
		if self.is_waiting_acceptance and not self.is_counteroffer:
			TradeStatus.objects.bulk_create(
				[
					TradeStatus(trade=self, actioned_by=participant, status=TradeStatuses.SENT)
					for participant in self.participants.all()
				],
			)

			Notification.objects.bulk_create(
				[
					Notification(
						user=participant.owner,
						message="A new trade has been proposed involving your team.",
						level="info",
						redirect_to=f"/trades/{self.pk}/",
					)
					for participant in self.participants.all()
				],
			)

			return

		# If the trade is a counteroffer and is the latest, mark the parent trade as done
		if self.is_counteroffer and self.parent and self.parent.is_latest:
			self.parent.done = True
			self.parent.save()

			Notification.objects.create(
				user=self.parent.sender.owner,
				message=f"A counteroffer has been made to your trade proposal by {self.sender.owner}.",
				level="info",
				redirect_to=f"/trades/{self.parent.pk}/",
			)

			return

		# If the trade is rejected, mark it as done
		if self.is_rejected:
			self.done = True

			Notification.objects.bulk_create(
				[
					Notification(
						user=participant.owner,
						message="A trade you are involved in has been rejected by one of the parties.",
						level="info",
						redirect_to=f"/trades/{self.pk}/",
					)
					for participant in self.participants.all()
				],
			)

			return

		# If the trade is accepted by all parties, notify everyone involved
		if self.is_accepted:
			# Commissioners, for review
			Notification.objects.bulk_create(
				[
					Notification(
						user=commissioner.owner,
						message="A trade has been accepted and requires your review as a commissioner.",
						level="info",
						redirect_to=f"/trades/{self.pk}/",
					)
					for commissioner in self.get_commissioners()
				],
			)

			# Participants, for information
			Notification.objects.bulk_create(
				[
					Notification(
						user=participant.owner,
						message="A trade you are involved in has been accepted by all parties.",
						level="info",
						redirect_to=f"/trades/{self.pk}/",
					)
					for participant in self.participants.all()
				],
			)

			# Create trade statuses for commissioners
			TradeStatus.objects.bulk_create(
				[
					TradeStatus(trade=self, actioned_by=commissioner, status=TradeStatuses.PENDING)
					for commissioner in self.get_commissioners()
				],
			)

			return

	def make_route(self, action: str, team: Team) -> None:
		"""
		Route the action to the appropriate method.

		Raises:
			ValidationError: If the action is invalid.

		Args:
			action (str): The action to perform.
			team (Team): The team performing the action.
		"""
		action_method_map = {
			TradeStatuses.REJECTED.value: self.make_reject,
			TradeStatuses.ACCEPTED.value: self.make_accept,
			TradeStatuses.APPROVED.value: self.make_approve,
			TradeStatuses.VETOED.value: self.make_veto,
		}

		if action not in action_method_map:
			raise ValidationError(f"Invalid action: {action}")

		return action_method_map[action](team)

	@atomic
	def make_counteroffer(self, offer: "Trade") -> "Trade":
		"""
		Create a counteroffer trade based on this trade.

		Args:
			offer (Trade): The trade offer to base the counteroffer on.

		Returns:
			Trade: The newly created counteroffer trade.
		"""
		counteroffer = Trade.objects.create(sender=offer.sender, parent=self)

		counteroffer.participants.set(self.participants.all())

		for asset in offer.assets.all():
			asset.pk = None  # Reset primary key to create a new object
			asset.trade = counteroffer
			asset.save()

		counteroffer.handle_changes()

		return counteroffer

	@atomic
	def make_accept(self, team: Team) -> None:
		"""
		Mark the trade as accepted by a participant.

		Args:
			team (Team): The team accepting the trade.
		"""
		TradeStatus.objects.create(trade=self, actioned_by=team, status=TradeStatuses.ACCEPTED)

		self.handle_changes()

	@atomic
	def make_reject(self, team: Team) -> None:
		"""
		Mark the trade as rejected by a participant.

		Args:
			team (Team): The team rejecting the trade.
		"""
		TradeStatus.objects.create(trade=self, actioned_by=team, status=TradeStatuses.REJECTED)

		self.handle_changes()

	@atomic
	def make_approve(self, team: Team) -> None:
		"""
		Mark the trade as approved by a commissioner or admin.

		Raises:
			ValidationError: If the team is not a commissioner or admin.

		Args:
			team (Team): The team approving the trade.
		"""
		if not team.owner.is_superuser and not team.owner.is_staff:
			raise ValidationError("Only commissioners or admins can approve trades.")

		TradeStatus.objects.create(trade=self, actioned_by=team, status=TradeStatuses.APPROVED)

		self.handle_changes()

	@atomic
	def make_veto(self, team: Team) -> None:
		"""
		Mark the trade as vetoed by a commissioner or admin.

		Raises:
			ValidationError: If the team is not a commissioner or admin.

		Args:
			team (Team): The team vetoing the trade.
		"""
		if not team.owner.is_superuser and not team.owner.is_staff:
			raise ValidationError("Only commissioners or admins can veto trades.")

		TradeStatus.objects.create(trade=self, actioned_by=team, status=TradeStatuses.VETOED)

		self.handle_changes()

	@property
	def is_latest(self) -> bool:
		"""Check if the trade is still active (not succeeded by another trade)."""
		return not self.succeeded_by.exists()

	@property
	def is_waiting_acceptance(self) -> bool:
		"""Check if the trade is waiting for acceptance from participants."""
		return self.is_latest and not self.is_accepted and not self.is_rejected

	@property
	def is_counteroffer(self) -> bool:
		"""Check if the trade is a counteroffer (has a parent trade)."""
		return self.parent is not None

	@property
	def is_accepted(self) -> bool:
		"""
		Check if all participants have accepted the trade.

		Returns:
			bool: True if all participants have accepted, False otherwise.
		"""
		statuses = self.statuses.all()
		accepted_status = TradeStatuses.ACCEPTED

		for participant in self.participants.all():
			participant_statuses = statuses.filter(actioned_by=participant).order_by("-created_at")

			if participant.id != self.sender.id and (
				not participant_statuses.exists() or participant_statuses.first().status != accepted_status
			):
				return False

		return self.participants.exists()

	@property
	def is_rejected(self) -> bool:
		"""
		Check if any participant has rejected the trade.

		Returns:
			bool: True if any participant has rejected, False otherwise.
		"""
		statuses = self.statuses.all()
		rejected_status = TradeStatuses.REJECTED

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
		approved_status = TradeStatuses.APPROVED

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

	@property
	def is_vetoed(self) -> bool:
		"""
		Check if the trade has been vetoed.
		A trade is vetoed if any admin or the majority of commissioners veto it.

		Returns:
			bool: True if the trade is vetoed, False otherwise.
		"""
		statuses = self.statuses.all()
		vetoed_status = TradeStatuses.VETOED

		# Check for admin veto
		for admin in self.get_admins():
			admin_statuses = statuses.filter(actioned_by=admin).order_by("-created_at")

			if admin_statuses.exists() and admin_statuses.first().status == vetoed_status:
				return True

		# Check for commissioner veto
		vetoes = 0
		total_commissioners = self.get_commissioners().count()

		for commissioner in self.get_commissioners():
			commissioner_statuses = statuses.filter(actioned_by=commissioner).order_by("-created_at")

			if commissioner_statuses.exists() and commissioner_statuses.first().status == vetoed_status:
				vetoes += 1

		return vetoes > total_commissioners / 2

	@property
	def is_finalized(self) -> bool:
		"""
		Check if the trade is finalized (accepted and approved).

		Returns:
			bool: True if the trade is finalized, False otherwise.
		"""
		return self.is_accepted and self.is_approved

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
	def accepted_by(self) -> QuerySet[Team]:
		"""
		Get all participants who have accepted the trade.

		Returns:
			QuerySet: A queryset of teams who have accepted the trade.
		"""
		accepted_status = TradeStatuses.ACCEPTED
		accepted_participants = []

		for participant in self.participants.all():
			participant_statuses = self.statuses.filter(actioned_by=participant).order_by("-created_at")

			if participant_statuses.exists() and participant_statuses.first().status == accepted_status:
				accepted_participants.append(participant)

		return Team.objects.filter(id__in=[team.id for team in accepted_participants])

	@property
	def rejected_by(self) -> QuerySet[Team]:
		"""
		Get all participants who have rejected the trade.

		Returns:
			QuerySet: A queryset of teams who have rejected the trade.
		"""
		rejected_status = TradeStatuses.REJECTED
		rejected_participants = []

		for participant in self.participants.all():
			participant_statuses = self.statuses.filter(actioned_by=participant).order_by("-created_at")

			if participant_statuses.exists() and participant_statuses.first().status == rejected_status:
				rejected_participants.append(participant)

		return Team.objects.filter(id__in=[team.id for team in rejected_participants])

	@property
	def timeline(self) -> list[TimelineEntry]:
		"""
		The timeline of the trade.

		Returns:
			list[TimelineEntry]: A list of timeline entries for the trade.
		"""
		timeline_entries: dict[str, TimelineEntry] = defaultdict(str)

		for status in self.statuses.all().order_by("created_at"):
			entry = self.construct_timeline_entry(status)

			if entry is None:
				continue

			hash_key = f"{entry.team.id if entry.team else 'none'}-{entry.action}-{entry.timestamp.isoformat()}"
			timeline_entries[hash_key] = entry

		# Sort timeline entries by timestamp
		return sorted(timeline_entries.values(), key=lambda x: x.timestamp)

	def get_commissioners(self) -> QuerySet[Team]:
		"""
		Get all commissioners associated with the league.

		Returns:
			QuerySet: A queryset of commissioner teams.
		"""
		return (
			Team.objects.filter(owner__in=User.objects.filter(is_staff=True).exclude(is_superuser=True))
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

	def construct_timeline_entry(self, entry: TradeStatus) -> Optional[TimelineEntry]:
		"""
		Construct a timeline entry for the trade.

		Args:
			entry (TradeStatus): The trade status entry to construct the timeline entry from.

		Raises:
			ValidationError: If the trade status is unknown.

		Returns:
			TimelineEntry: The constructed timeline entry.
		"""
		team = None
		action = None
		description = None

		if entry.status == TradeStatuses.SENT and self.sender == entry.actioned_by:
			action = "counteroffered" if self.is_counteroffer else "proposed"
			description = (
				f"A {'counteroffer' if self.is_counteroffer else 'trade'} was proposed by {entry.actioned_by}."
			)

		elif entry.status == TradeStatuses.ACCEPTED:
			action = TradeStatuses.ACCEPTED
			description = f"The trade was accepted by {entry.actioned_by}."

		elif entry.status == TradeStatuses.REJECTED:
			action = TradeStatuses.REJECTED
			description = f"The trade was rejected by {entry.actioned_by}."

		elif self.is_approved:
			action = TradeStatuses.APPROVED
			description = "The trade was approved."

		elif self.is_vetoed:
			action = TradeStatuses.VETOED
			description = "The trade was vetoed."

		if action not in {TradeStatuses.APPROVED, TradeStatuses.VETOED}:
			team = entry.actioned_by

		if action is None or description is None:
			if entry.status not in {TradeStatuses.PENDING, TradeStatuses.SENT}:
				raise ValidationError(f"Unknown trade status for timeline entry: {entry.status}")

			return None

		return Box(
			TimelineEntry(
				team=team,
				action=action,
				timestamp=entry.created_at,
				description=description,
			),
		)
