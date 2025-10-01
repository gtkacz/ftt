from collections.abc import Sequence
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from ftt.settings import LEAGUE_SETTINGS


class Trade(models.Model):
	"""Model representing a trade between teams in a fantasy league."""

	STATUS_CHOICES = [
		("draft", "Draft"),  # Being composed
		("proposed", "Proposed"),  # Sent to other teams
		("accepted", "Accepted"),  # All teams accepted
		("rejected", "Rejected"),  # At least one team rejected
		("cancelled", "Cancelled"),  # Cancelled by proposer
		("waiting_approval", "Waiting for Approval"),  # Needs commissioner approval
		("approved", "Approved"),  # Commissioner approved
		("completed", "Completed"),  # Trade has been executed
		("vetoed", "Vetoed"),  # Commissioner vetoed
	]

	# The team that initiated the trade
	proposing_team = models.ForeignKey(
		"Team",
		on_delete=models.CASCADE,
		related_name="proposed_trades",
		help_text="Team that proposed this trade",
	)

	# All teams involved in the trade (including proposer)
	teams = models.ManyToManyField(
		"Team",
		related_name="trades",
		help_text="All teams involved in the trade",
	)

	status = models.CharField(
		max_length=20,
		choices=STATUS_CHOICES,
		default="draft",
		help_text="Current status of the trade",
	)

	# Timestamps
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	proposed_at = models.DateTimeField(
		blank=True,
		null=True,
		help_text="When the trade was proposed to other teams",
	)
	completed_at = models.DateTimeField(
		blank=True,
		null=True,
		help_text="When the trade was executed",
	)
	approved_at = models.DateTimeField(
		blank=True,
		null=True,
		help_text="When the trade was approved by commissioner",
	)

	# Commissioner approval tracking
	approved_by = models.ForeignKey(
		"User",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="approved_trades",
		help_text="Commissioner who approved the trade",
	)

	# Notes/messages
	notes = models.TextField(
		blank=True,
		help_text="Optional notes about the trade",
	)

	class Meta:  # noqa: D106
		ordering = ("-created_at",)
		indexes = [
			models.Index(fields=["status"]),
			models.Index(fields=["proposing_team", "status"]),
			models.Index(fields=["-created_at"]),
		]

	def __str__(self) -> str:
		team_names = ", ".join(str(team) for team in self.teams.all()[:3])
		return f"Trade {self.id} ({team_names}) - {self.get_status_display()}"  # pyright: ignore[reportAttributeAccessIssue]

	def clean(self) -> None:
		"""Validate the trade before saving."""
		super().clean()

		# Only validate when moving to accepted/approved status
		if self.status in ["accepted", "approved", "completed"]:
			# Check cap compliance for all teams
			for team in self.teams.all():
				try:
					self._validate_team_caps(team)
				except ValidationError as e:
					raise ValidationError(f"Trade invalid for {team.name}: {e.message}") from e

			# Validate all traded players
			for asset in self.assets.filter(asset_type="player"):
				self._validate_player_tradeable(asset)

	def _validate_team_caps(self, team: "Team") -> None:  # noqa: F821
		"""Validate that team won't exceed caps after trade."""
		incoming_salary = sum(
			asset.player.contract.salary
			for asset in self.assets.filter(receiving_team=team, asset_type="player")
			if asset.player and hasattr(asset.player, "contract")
		)
		outgoing_salary = sum(
			asset.player.contract.salary
			for asset in self.assets.filter(giving_team=team, asset_type="player")
			if asset.player and hasattr(asset.player, "contract")
		)

		incoming_players = self.assets.filter(receiving_team=team, asset_type="player").count()
		outgoing_players = self.assets.filter(giving_team=team, asset_type="player").count()

		net_salary = incoming_salary - outgoing_salary
		net_players = incoming_players - outgoing_players

		# Check salary cap
		if team.total_salary() + net_salary > LEAGUE_SETTINGS.SALARY_CAP:
			raise ValidationError(
				f"{team.name} would exceed salary cap. "
				f"Current: {team.total_salary()}, Net change: {net_salary}, "
				f"Cap: {LEAGUE_SETTINGS.SALARY_CAP}"
			)

		# Check player cap
		if team.total_players() + net_players > LEAGUE_SETTINGS.MAX_PLAYER_CAP:
			raise ValidationError(
				f"{team.name} would exceed player cap. "
				f"Current: {team.total_players()}, Net change: {net_players}, "
				f"Cap: {LEAGUE_SETTINGS.MAX_PLAYER_CAP}"
			)

	def _validate_player_tradeable(self, asset: "TradeAsset") -> None:  # noqa: F821
		"""Validate that a player can be traded."""
		if not asset.player:
			return

		player = asset.player
		giving_team = asset.giving_team

		# Check if player has a contract
		if not hasattr(player, "contract"):
			raise ValidationError(f"{player} has no contract and cannot be traded")

		contract = player.contract

		# Validate the giving team owns the player's rights
		if contract.team != giving_team:
			# Special case: RFA players can be traded by rights owner
			if not contract.is_rfa:
				raise ValidationError(f"{player} is not owned by {giving_team.name}")

			# For RFA, check if giving_team owns the rights
			if contract.team != giving_team:
				raise ValidationError(f"{giving_team.name} does not own rights to RFA {player}")

		# Check if player is RFA-only (0 years left)
		current_year = timezone.now().year
		years_remaining = (contract.start_year + contract.duration) - current_year

		if years_remaining <= 0 and not contract.is_rfa:
			raise ValidationError(
				f"{player} has {years_remaining} years remaining and is not an RFA. "
				"Only RFA players with 0 years can be traded."
			)

	@transaction.atomic
	def propose(self) -> None:
		"""Propose the trade to all involved teams."""
		if self.status != "draft":
			raise ValidationError(f"Cannot propose trade with status {self.status}")

		self.status = "proposed"
		self.proposed_at = timezone.now()
		self.save()

		# Create initial offer for all teams
		for team in self.teams.all():
			TradeOffer.objects.create(
				trade=self,
				team=team,
				is_proposer=(team == self.proposing_team),
				status="accepted" if team == self.proposing_team else "pending",
			)

	@transaction.atomic
	def execute(self) -> None:
		"""Execute the trade by transferring assets between teams."""
		if self.status not in ["accepted", "approved"]:
			raise ValidationError(f"Cannot execute trade with status {self.status}")

		# Perform full clean before execution
		self.full_clean()

		# Transfer players
		for asset in self.assets.filter(asset_type="player"):
			if asset.player and hasattr(asset.player, "contract"):
				asset.player.contract.team = asset.receiving_team
				asset.player.contract.save()

		# Transfer picks
		for asset in self.assets.filter(asset_type="pick"):
			if asset.pick:
				asset.pick.current_team = asset.receiving_team

				# Apply protections if specified in the trade
				if asset.pick_protection_type and asset.pick_protection_type != "none":
					asset.pick.protection_type = asset.pick_protection_type

					if asset.pick_protection_type == "doesnt_convey":
						asset.pick.protection_range_start = asset.pick_protection_range_start
						asset.pick.protection_range_end = asset.pick_protection_range_end
						asset.pick.rollover_year = asset.pick_rollover_year

					elif asset.pick_protection_type in ["swap_best", "swap_worst"]:
						asset.pick.swap_target_pick = asset.pick_swap_target

				asset.pick.save()

		# Update trade status
		self.status = "completed"
		self.completed_at = timezone.now()
		self.save()

	def get_team_assets(self, team: "Team") -> dict[str, Any]:  # noqa: F821
		"""Get all assets being given and received by a specific team."""
		return {
			"giving": {
				"players": list(self.assets.filter(giving_team=team, asset_type="player").select_related("player")),
				"picks": list(self.assets.filter(giving_team=team, asset_type="pick").select_related("pick")),
			},
			"receiving": {
				"players": list(
					self.assets.filter(receiving_team=team, asset_type="player").select_related("player")
				),
				"picks": list(self.assets.filter(receiving_team=team, asset_type="pick").select_related("pick")),
			},
		}

	def all_teams_accepted(self) -> bool:
		"""Check if all teams have accepted the trade."""
		total_teams = self.teams.count()
		accepted_offers = self.offers.filter(status="accepted").count()
		return total_teams > 0 and accepted_offers == total_teams


class TradeOffer(models.Model):
	"""Model representing a team's response to a trade offer."""

	STATUS_CHOICES = [
		("pending", "Pending"),
		("accepted", "Accepted"),
		("rejected", "Rejected"),
		("countered", "Countered"),
	]

	trade = models.ForeignKey(
		Trade,
		on_delete=models.CASCADE,
		related_name="offers",
		help_text="The trade this offer is for",
	)

	team = models.ForeignKey(
		"Team",
		on_delete=models.CASCADE,
		related_name="trade_offers",
		help_text="Team making this offer/response",
	)

	status = models.CharField(
		max_length=20,
		choices=STATUS_CHOICES,
		default="pending",
		help_text="Status of this team's response",
	)

	is_proposer = models.BooleanField(
		default=False,
		help_text="Whether this team proposed the trade",
	)

	# Counter-offer tracking
	counter_offer = models.ForeignKey(
		"self",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="original_offer",
		help_text="If this is a counter-offer, reference to the offer it counters",
	)

	message = models.TextField(
		blank=True,
		help_text="Optional message with the offer",
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	responded_at = models.DateTimeField(
		null=True,
		blank=True,
		help_text="When the team responded to the offer",
	)

	class Meta:  # noqa: D106
		ordering = ("-created_at",)
		indexes = [
			models.Index(fields=["trade", "team"]),
			models.Index(fields=["status"]),
		]

	def __str__(self) -> str:
		return f"{self.team} - {self.get_status_display()} for Trade {self.trade_id}"

	def accept(self, message: str = "") -> None:
		"""Accept the trade offer."""
		self.status = "accepted"
		self.message = message
		self.responded_at = timezone.now()
		self.save()

		# Check if all teams accepted
		if self.trade.all_teams_accepted():
			self.trade.status = "accepted"
			self.trade.save()

	def reject(self, message: str = "") -> None:
		"""Reject the trade offer."""
		self.status = "rejected"
		self.message = message
		self.responded_at = timezone.now()
		self.save()

		# Update trade status
		self.trade.status = "rejected"
		self.trade.save()

	def counter(self, message: str = "") -> "Trade":
		"""Create a counter-offer (new trade based on this one)."""
		# Mark this offer as countered
		self.status = "countered"
		self.message = message
		self.responded_at = timezone.now()
		self.save()

		# Create new trade as counter-offer
		new_trade = Trade.objects.create(
			proposing_team=self.team,
			status="draft",
			notes=f"Counter-offer to Trade {self.trade_id}",
		)

		# Copy teams
		new_trade.teams.set(self.trade.teams.all())

		# Create counter-offer link
		TradeOffer.objects.create(
			trade=new_trade,
			team=self.team,
			is_proposer=True,
			counter_offer=self,
			status="accepted",
		)

		return new_trade


class TradeAsset(models.Model):
	"""Model representing an asset (player or pick) being traded."""

	ASSET_TYPE_CHOICES = [
		("player", "Player"),
		("pick", "Pick"),
	]

	trade = models.ForeignKey(
		Trade,
		on_delete=models.CASCADE,
		related_name="assets",
		help_text="The trade this asset is part of",
	)

	asset_type = models.CharField(
		max_length=10,
		choices=ASSET_TYPE_CHOICES,
		help_text="Type of asset being traded",
	)

	# Team giving the asset
	giving_team = models.ForeignKey(
		"Team",
		on_delete=models.CASCADE,
		related_name="assets_given",
		help_text="Team giving up this asset",
	)

	# Team receiving the asset
	receiving_team = models.ForeignKey(
		"Team",
		on_delete=models.CASCADE,
		related_name="assets_received",
		help_text="Team receiving this asset",
	)

	# Asset references (only one should be set based on asset_type)
	player = models.ForeignKey(
		"Player",
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name="trade_assets",
		help_text="Player being traded (if asset_type is 'player')",
	)

	pick = models.ForeignKey(
		"draft.Pick",
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name="trade_assets",
		help_text="Pick being traded (if asset_type is 'pick')",
	)

	# Pick-specific protection fields
	pick_protection_type = models.CharField(
		max_length=20,
		blank=True,
		default="none",
		help_text="Type of protection on traded pick (none, swap_best, swap_worst, doesnt_convey)",
	)

	pick_protection_range_start = models.PositiveIntegerField(
		null=True,
		blank=True,
		help_text="Start of protected range for doesnt_convey (e.g., 1 for top-5)",
	)

	pick_protection_range_end = models.PositiveIntegerField(
		null=True,
		blank=True,
		help_text="End of protected range for doesnt_convey (e.g., 5 for top-5)",
	)

	pick_swap_target = models.ForeignKey(
		"draft.Pick",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="swap_trade_assets",
		help_text="Pick to swap with for swap_best/swap_worst",
	)

	pick_rollover_year = models.PositiveIntegerField(
		null=True,
		blank=True,
		help_text="Year to roll over to if pick doesn't convey",
	)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:  # noqa: D106
		ordering = ("asset_type", "created_at")
		indexes = [
			models.Index(fields=["trade", "asset_type"]),
			models.Index(fields=["giving_team"]),
			models.Index(fields=["receiving_team"]),
		]

	def __str__(self) -> str:
		if self.asset_type == "player" and self.player:
			return f"{self.player} from {self.giving_team} to {self.receiving_team}"
		elif self.asset_type == "pick" and self.pick:
			protection = self._get_protection_display()
			return f"{self.pick} from {self.giving_team} to {self.receiving_team}{protection}"
		return f"Unknown asset from {self.giving_team} to {self.receiving_team}"

	def _get_protection_display(self) -> str:
		"""Generate protection display string for pick trades."""
		if self.pick_protection_type == "none" or not self.pick_protection_type:
			return ""

		if self.pick_protection_type == "doesnt_convey":
			if self.pick_protection_range_start and self.pick_protection_range_end:
				return f" (Doesn't convey picks {self.pick_protection_range_start}-{self.pick_protection_range_end})"
			return " (Doesn't convey - protected)"

		if self.pick_protection_type == "swap_best" and self.pick_swap_target:
			return f" (Swap to best with {self.pick_swap_target.original_team.name})"

		if self.pick_protection_type == "swap_worst" and self.pick_swap_target:
			return f" (Swap to worst with {self.pick_swap_target.original_team.name})"

		return f" ({self.pick_protection_type})"

	def clean(self) -> None:
		"""Validate the asset."""
		super().clean()

		# Validate that the correct asset is set
		if self.asset_type == "player" and not self.player:
			raise ValidationError("Player must be set when asset_type is 'player'")
		if self.asset_type == "pick" and not self.pick:
			raise ValidationError("Pick must be set when asset_type is 'pick'")

		# Validate that only one asset is set
		if self.player and self.pick:
			raise ValidationError("Cannot have both player and pick set")

		# Validate pick protections
		if self.asset_type == "pick" and self.pick_protection_type != "none":
			if self.pick_protection_type in ["swap_best", "swap_worst"]:
				if not self.pick_swap_target:
					raise ValidationError(
						f"pick_swap_target required for protection type '{self.pick_protection_type}'"
					)

				if self.pick_swap_target == self.pick:
					raise ValidationError("Cannot swap pick with itself")

			if self.pick_protection_type == "doesnt_convey":
				if not self.pick_protection_range_start or not self.pick_protection_range_end:
					raise ValidationError(
						"pick_protection_range_start and pick_protection_range_end required for doesnt_convey"
					)

				if self.pick_protection_range_start > self.pick_protection_range_end:
					raise ValidationError("pick_protection_range_start must be <= pick_protection_range_end")

				if not self.pick_rollover_year:
					raise ValidationError("pick_rollover_year required for doesnt_convey protection")

				if self.pick and self.pick_rollover_year <= self.pick.draft_year:
					raise ValidationError("pick_rollover_year must be after pick's draft_year")

	def save(self, *args: Sequence[Any], **kwargs: dict[str, Any]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
		"""Save the asset with validation."""
		self.full_clean()
		return super().save(*args, **kwargs)  # pyright: ignore[reportArgumentType]
