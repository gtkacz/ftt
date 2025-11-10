import logging
from datetime import datetime, time, timedelta
from json import loads
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from core.models import Contract, Notification, Player, Team
from draft.models.pick import Pick
from ftt.common.util import get_number_suffix

logger = logging.getLogger(__name__)


class DraftPick(models.Model):
	"""The concrete pick in a draft."""

	draft = models.ForeignKey("Draft", on_delete=models.CASCADE, related_name="draft_positions")
	pick = models.ForeignKey(
		"Pick",
		on_delete=models.CASCADE,
		related_name="draft_positions",
		null=True,
		blank=True,
	)
	pick_number = models.PositiveIntegerField(help_text="Pick number within the round")
	overall_pick = models.PositiveIntegerField(help_text="Overall pick number in draft")
	selected_player = models.ForeignKey("core.Player", on_delete=models.SET_NULL, null=True, blank=True)
	started_at = models.DateTimeField(null=True, blank=True, help_text="Time when the pick was started")
	is_pick_made = models.BooleanField(default=False)
	pick_made_at = models.DateTimeField(null=True, blank=True)
	is_current = models.BooleanField(default=False)
	is_auto_pick = models.BooleanField(default=False)
	contract = models.OneToOneField(
		"core.Contract",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="draft_pick",
		help_text="Contract associated with the drafted player",
	)

	class Meta:
		ordering = ("draft", "pick")
		unique_together = ("draft", "pick")
		constraints = (
			models.UniqueConstraint(
				fields=["draft"],
				condition=models.Q(is_current=1),
				name="only_one_current_pick_per_draft",
			),
		)

	def __str__(self) -> str:
		return f"{self.draft.year} Draft - Round {self.pick.round_number}, Pick {self.pick_number} ({self.pick.current_team.name})"  # pyright: ignore[reportAttributeAccessIssue]

	def save(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
		"""Override save to handle pick protection transfer."""
		if self.pick and self.draft:
			self._handle_draft_pick_transfer()

		super().save(*args, **kwargs)

	def _get_paired_pick(self) -> Pick:
		"""
		Gets the draft pick that is paired with this pick for swap protection.

		Raises:
			ValidationError: If no paired pick is found.

		Returns:
			Pick: The paired draft pick if it exists, otherwise None.
		"""
		metadata = loads(self.pick.metadata) if isinstance(self.pick.metadata, str) else self.pick.metadata

		paired_pick_info = metadata.get("swapped_with_pick_id", None)

		if paired_pick_info is None:
			raise ValidationError("No paired pick found for swap protection.")

		pick = Pick.objects.filter(id=paired_pick_info)

		if not pick.exists():
			raise ValidationError("No paired pick found for swap protection.")

		return pick.first()

	def _handle_draft_pick_transfer(self) -> None:  # noqa: PLR0911
		"""
		Handles the transfer of a draft pick to the receiver team.

		Raises:
			ValidationError: If the protection type is unknown.

		This method updates the team associated with the draft pick.
		"""
		if not self.is_part_of_trade or self.pick.protection_conveyed:
			return

		if self.pick.protection == Pick.ProtectionChoices.UNPROTECTED.value[0]:
			self.pick.protection_conveyed = True
			return

		if self.pick.protection == Pick.ProtectionChoices.TOP_X.value[0]:
			if self.overall_pick > self.pick.top_x_value:
				metadata = (
					loads(self.pick.protection_metadata)
					if isinstance(self.pick.protection_metadata, str)
					else self.pick.protection_metadata
				)

				conveys_to_team_id = metadata.get("conveys_to_team_id", None)

				if conveys_to_team_id is None:
					raise ValidationError("conveys_to_team_id is missing in protection metadata for TOP_X protection.")

				conveys_to = Team.objects.get(id=conveys_to_team_id)

				self.pick.current_team = conveys_to
				self.pick.protection_conveyed = True

			return

		if self.pick.protection == Pick.ProtectionChoices.SWAP_BEST.value[0]:
			paired_pick = self._get_paired_pick()

			if self.overall_pick < paired_pick.draft_positions.overall_pick:
				return

			paired_team = paired_pick.current_team

			paired_pick.current_team = self.pick.current_team
			paired_pick.protection_conveyed = True

			self.pick.current_team = paired_team
			self.pick.protection_conveyed = True

			paired_pick.save()

			return

		if self.pick.protection == Pick.ProtectionChoices.SWAP_WORST.value[0]:
			paired_pick = self._get_paired_pick()

			if self.overall_pick > paired_pick.draft_positions.overall_pick:
				return

			paired_team = paired_pick.current_team

			paired_pick.current_team = self.pick.current_team
			paired_pick.protection_conveyed = True

			self.pick.current_team = paired_team
			self.pick.protection_conveyed = True

			paired_pick.save()

			return

		raise ValidationError("Unknown draft pick protection type.")

	def generate_contract(self) -> Contract:  # noqa: C901, PLR0912
		"""
		Generate a contract for the drafted player based on the pick number and round number.

		Raises:
			ValueError: If pick number or round number is not set.

		Returns:
			Contract: The generated contract for the drafted player.
		"""
		if not self.pick or not self.pick_number or not self.pick.round_number:
			raise ValueError("Pick number and round number must be set to generate a contract")

		data = {}

		if self.draft.is_league_draft:
			if self.pick.round_number == 1:
				data = {
					"duration": 2,
					"salary": 25,
				}

			elif self.pick.round_number == 2:
				data = {
					"duration": 2,
					"salary": 20,
				}

			elif self.pick.round_number == 3:
				data = {
					"duration": 2,
					"salary": 15,
				}

			elif self.pick.round_number == 4:
				data = {
					"duration": 2,
					"salary": 12,
				}

			elif self.pick.round_number == 5:
				data = {
					"duration": 2,
					"salary": 8.5,
				}

			elif self.pick.round_number == 6:
				data = {
					"duration": 1,
					"salary": 8.5,
					"is_to": True,
				}

			elif self.pick.round_number == 7:
				data = {
					"duration": 1,
					"salary": 7.5,
					"is_to": True,
				}

			elif self.pick.round_number in {8, 9, 10}:
				data = {
					"duration": 1,
					"salary": 5,
					"is_to": True,
				}

			elif self.pick.round_number in {11, 12, 13}:
				data = {
					"duration": 2,
					"salary": 3.5,
				}

			elif self.pick.round_number == 14:
				data = {
					"duration": 2,
					"salary": 2,
				}

			else:
				data = {
					"duration": 2,
					"salary": 2,
				}

		return Contract.objects.create(
			player=self.selected_player,
			team=self.pick.current_team,
			start_year=self.draft.year,
			**data,
		)

	def time_left_to_pick(self) -> int:
		"""Calculates the time left for the current pick in seconds."""  # noqa: DOC201
		if not self.started_at or not self.is_current:
			return self.draft.time_limit_per_pick * 60  # Convert minutes to seconds

		# Calculate when the pick deadline will be
		deadline = self._calculate_pick_deadline(self.started_at, self.draft.time_limit_per_pick)

		# Return seconds between now and the deadline
		now = timezone.now()
		if now >= deadline:
			return 0

		return round((deadline - now).total_seconds())

	def can_pick_until(self) -> datetime:
		"""Calculates the datetime until which the pick can be made."""  # noqa: DOC201
		if not self.started_at or not self.is_current:
			return timezone.now() + timedelta(minutes=self.draft.time_limit_per_pick)

		return self._calculate_pick_deadline(self.started_at, self.draft.time_limit_per_pick)

	def _calculate_pick_deadline(self, start_time: datetime, limit_minutes: int) -> datetime:
		"""Calculate when the pick deadline will be, accounting for active hours."""  # noqa: DOC201
		lower_bound = self.draft.pick_hour_lower_bound
		upper_bound = self.draft.pick_hour_upper_bound
		app_timezone = ZoneInfo(str(timezone.get_current_timezone()))

		remaining_seconds = limit_minutes * 60
		current_time = start_time

		while remaining_seconds > 0:
			current_date = current_time.date()

			# Create the active window for current date using app timezone
			window_start = datetime.combine(current_date, time(lower_bound, 0))
			window_start = window_start.astimezone(app_timezone)

			window_end = datetime.combine(current_date, time(upper_bound, 0))
			window_end = window_end.astimezone(app_timezone)

			# If we're before the window, jump to window start
			if current_time < window_start:
				current_time = window_start
			# If we're after the window, jump to next day's window start
			elif current_time >= window_end:
				next_date = current_date + timedelta(days=1)
				next_window_start = datetime.combine(next_date, time(lower_bound, 0))
				current_time = next_window_start.astimezone(app_timezone)
				continue

			# Calculate how much time we can use in this window
			time_until_window_end = (window_end - current_time).total_seconds()

			if remaining_seconds <= time_until_window_end:
				# We can finish within this window
				return current_time + timedelta(seconds=remaining_seconds)

			remaining_seconds -= time_until_window_end
			next_date = current_date + timedelta(days=1)
			next_window_start = datetime.combine(next_date, time(lower_bound, 0))
			current_time = next_window_start.astimezone(app_timezone)

		return current_time

	def remaining_seconds(self) -> int:
		"""Calculates the time left for the current pick in seconds."""  # noqa: DOC201
		if not self.started_at or not self.is_current:
			return self.draft.time_limit_per_pick * 60  # Convert minutes to seconds

		now = timezone.now()
		total_limit_seconds = self.draft.time_limit_per_pick * 60
		elapsed_active_seconds = self._get_elapsed_active_seconds(self.started_at, now)

		return max(0, total_limit_seconds - elapsed_active_seconds)

	def _get_elapsed_active_seconds(self, start_time: datetime, end_time: datetime) -> int:
		"""Calculate active seconds elapsed between start_time and end_time."""  # noqa: DOC201
		if start_time >= end_time:
			return 0

		lower_bound = self.draft.pick_hour_lower_bound
		upper_bound = self.draft.pick_hour_upper_bound
		app_timezone = ZoneInfo(str(timezone.get_current_timezone()))

		total_seconds = 0
		current_date = start_time.date()

		while current_date <= end_time.date():
			# Create the active window for this date using app timezone
			window_start = datetime.combine(current_date, time(lower_bound, 0))
			window_start = window_start.astimezone(app_timezone)

			window_end = datetime.combine(current_date, time(upper_bound, 0))
			window_end = window_end.astimezone(app_timezone)

			# Find intersection with our time range
			range_start = max(start_time, window_start)
			range_end = min(end_time, window_end)

			if range_start < range_end:
				total_seconds += (range_end - range_start).total_seconds()

			current_date += timedelta(days=1)

		return round(total_seconds)

	def make_pick(self, player: Player | None, *, is_auto_pick: bool = False) -> Player:  # noqa: C901, PLR0912, PLR0915
		"""Make a pick for the draft position."""  # noqa: DOC201, DOC501
		from draft.models.draft_queue import DraftQueue

		if self.time_left_to_pick() <= 0:
			is_auto_pick = True

			player = None

			if DraftQueue.objects.filter(team=self.pick.current_team, draft=self.draft).exists():  # pyright: ignore[reportAttributeAccessIssue]
				queue = DraftQueue.objects.get(team=self.pick.current_team, draft=self.draft)  # pyright: ignore[reportAttributeAccessIssue]

				if queue.autopick_enabled and queue.queue_items:
					player = queue.get_next_player()

			if not player:
				players = self.draft.current_player_pool().filter(real_team__isnull=False).values("id", "metadata")
				players = [{**loads(player["metadata"]), "id": player["id"]} for player in players]

				player_ = max(
					players,
					key=lambda p: p.get("total_fpts", 0) or p.get("fpts", 0),
				)
				player = Player.objects.get(id=player_["id"])

			logger.debug(f"Auto-picking player {player.nba_id} for pick {self.overall_pick}")

		if not player or not self.contract or not self.pick or not self.draft:
			raise ValueError("Invalid pick")

		if self.is_pick_made:
			raise ValueError("Pick has already been made")

		if not self.draft.current_player_pool().filter(id=player.id).exists():  # pyright: ignore[reportAttributeAccessIssue]
			raise ValueError("Player is not available for drafting")

		if not self.is_current:
			raise ValueError("Draft pick is not current")

		next_pick: DraftPick = self.draft.draft_positions.filter(overall_pick=self.overall_pick + 1).first()

		with transaction.atomic():
			self.selected_player = player
			self.is_pick_made = True
			self.pick_made_at = timezone.now()
			self.is_auto_pick = is_auto_pick
			self.is_current = False

			self.contract.player = player  # pyright: ignore[reportAttributeAccessIssue]
			self.contract.team = self.pick.current_team

			self.draft.draftable_players.remove(player)

			self.save()
			self.contract.save()
			self.draft.save()

			for queue in self.draft.team_queues.filter(autopick_enabled=True):
				if queue.queue_items:
					queue.updated_at = timezone.now()
					queue.save()

			if next_pick:
				next_pick.is_current = True
				next_pick.started_at = timezone.now()
				next_pick.save()

				self.send_pick_notifications(next_pick)

				queue = DraftQueue.objects.filter(team=next_pick.pick.current_team, draft=self.draft).first()  # pyright: ignore[reportOptionalMemberAccess]

				if queue and queue.autopick_enabled:
					for _ in range(len(queue.queue_items)):  # pyright: ignore[reportArgumentType]
						next_player = queue.get_next_player()

						if next_player and (next_player == player or hasattr(next_player, "contract")):
							queue.remove_player(next_player)
							next_player = queue.get_next_player()

						if next_player:
							queue.remove_player(next_player)
							next_pick.make_pick(next_player, is_auto_pick=True)
							Notification.objects.create(
								user=next_pick.pick.current_team.owner,  # pyright: ignore[reportOptionalMemberAccess]
								message=f"Your team has automatically picked {next_player} from the draft queue.",
								level="warning",
							)
							break

			else:
				self.draft.is_completed = True
				self.draft.save()
				Notification.objects.bulk_create(
					Notification(
						user=team.owner,
						message=f"The {self.draft.year} {'league' if self.draft.is_league_draft else ''} draft has been completed!",
						level="success",
					)
					for team in self.draft.teams.all()
				)

		return self.selected_player

	def send_pick_notifications(self, draft_pick: "DraftPick") -> None:
		"""Send notifications to the team about the current pick."""
		pick_limit = (
			self.draft.time_limit_per_pick / 60
			if self.draft.time_limit_per_pick / 60 != self.draft.time_limit_per_pick // 60
			else self.draft.time_limit_per_pick // 60
		)
		Notification.objects.create(
			user=draft_pick.pick.current_team.owner,  # pyright: ignore[reportAttributeAccessIssue]
			message=f"Your team is now on the clock for the {draft_pick.overall_pick}{get_number_suffix(draft_pick.overall_pick)} pick in the {self.draft.year} {'league' if self.draft.is_league_draft else ''} draft. You have {pick_limit} hour{'s' if pick_limit != 1 else ''} to make your pick.",
			level="warning",
		)

		for pick in range(draft_pick.overall_pick + 1, draft_pick.overall_pick + 6):
			next_pick = self.draft.draft_positions.filter(overall_pick=pick)

			if not next_pick.exists():
				continue

			next_pick = next_pick.first()

			Notification.objects.create(
				user=next_pick.pick.current_team.owner,
				message=f"Your team will be on the clock in {next_pick.overall_pick - draft_pick.overall_pick} picks in the {self.draft.year} {'league' if self.draft.is_league_draft else ''} draft.",
				level="info",
			)

	@property
	def is_part_of_trade(self) -> bool:
		"""Check if the draft pick is currently part of a trade."""
		from trade.models.trade import Trade
		from trade.models.trade_asset import TradeAsset

		assets = TradeAsset.objects.filter(draft_pick=self)
		trades = Trade.objects.filter(assets__in=assets)

		if not assets.exists() or not trades.exists():
			return False

		return any(trade.is_finalized for trade in trades)
