from json import loads

from django.core.exceptions import ValidationError
from django.db import models, transaction

from core.models import Contract
from draft.models import Pick


class TradeAsset(models.Model):
	"""A tradeable asset (player contract or draft pick) in the league."""

	sender = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="trade_assets")
	receiver = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="received_trade_assets")
	trade = models.ForeignKey("trade.Trade", on_delete=models.CASCADE, related_name="assets")
	asset_type = models.CharField(max_length=20, choices=[("player", "Player"), ("pick", "Draft Pick")])
	player_contract = models.ForeignKey(
		Contract,
		null=True,
		blank=True,
		on_delete=models.CASCADE,
		related_name="trade_assets",
	)
	draft_pick = models.ForeignKey(Pick, null=True, blank=True, on_delete=models.CASCADE, related_name="trade_assets")

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ("created_at", "updated_at")
		indexes = (models.Index(fields=["sender", "receiver"]), models.Index(fields=["trade"]))

	def __str__(self) -> str:
		return f"TradeAsset ({self.asset_type}) from {self.sender.name} to {self.receiver.name}"

	@property
	def asset(self) -> models.Model:
		"""
		The underlying asset (player contract or draft pick).

		Raises:
			ValidationError: Unknown asset type.

		Returns:
			models.Model: The asset.
		"""
		if self.asset_type == "player":
			return self.player_contract

		if self.asset_type == "pick":
			return self.draft_pick

		raise ValidationError("Unknown asset type.")

	def _handle_draft_pick_transfer(self) -> None:
		"""
		Handles the transfer of a draft pick to the receiver team.

		Raises:
			ValidationError: If the protection type is unknown.

		This method updates the team associated with the draft pick.
		"""
		self.draft_pick.team = self.receiver

		if self.draft_pick.protection == Pick.ProtectionChoices.UNPROTECTED.value[0]:
			return

		if self.draft_pick.protection == Pick.ProtectionChoices.TOP_X.value[0]:
			_ = self.draft_pick.top_x_value

			metadata = (
				loads(self.draft_pick.protection_metadata)
				if isinstance(self.draft_pick.protection_metadata, str)
				else self.draft_pick.protection_metadata
			)

			metadata["conveys_to_team_id"] = self.receiver.id
			self.draft_pick.protection_metadata = metadata

			return

		if self.draft_pick.protection == Pick.ProtectionChoices.SWAP_BEST.value[0]:
			paired_pick = self._get_paired_pick()
			self._swap_picks(paired_pick, is_best=True)
			return

		if self.draft_pick.protection == Pick.ProtectionChoices.SWAP_WORST.value[0]:
			paired_pick = self._get_paired_pick()
			self._swap_picks(paired_pick, is_best=False)
			return

		raise ValidationError("Unknown draft pick protection type.")

	def _get_paired_pick(self) -> Pick:
		"""
		Gets the draft pick that is paired with this pick for swap protection.

		Raises:
			ValidationError: If no paired pick is found.

		Returns:
			Pick: The paired draft pick if it exists, otherwise None.
		"""
		draft_year = self.draft_pick.draft_year
		round_number = self.draft_pick.round_number

		pick = Pick.objects.filter(
			is_from_league_draft=False,
			original_team=self.receiver,
			current_team=self.receiver,
			draft_year=draft_year,
			round_number=round_number,
		)

		if not pick.exists():
			raise ValidationError("No paired pick found for swap protection.")

		return pick.first()

	def _swap_picks(self, other_pick: Pick, *, is_best: bool = True) -> None:
		"""
		Swaps this draft pick with another draft pick.

		Args:
			other_pick (Pick): The draft pick to swap with.
			is_best (bool): If True, swap the best pick; otherwise, swap the worst pick.
		"""
		metadata = {"swapped_with_pick_id": other_pick.id}
		other_metadata = {"swapped_with_pick_id": self.draft_pick.id}

		if is_best:
			metadata["swap_type"] = "best"
			other_metadata["swap_type"] = "worse"

			self.draft_pick.protection = Pick.ProtectionChoices.SWAP_BEST.value[0]
			other_pick.protection = Pick.ProtectionChoices.SWAP_BEST.value[0]

		else:
			metadata["swap_type"] = "worse"
			other_metadata["swap_type"] = "best"

			self.draft_pick.protection = Pick.ProtectionChoices.SWAP_WORST.value[0]
			other_pick.protection = Pick.ProtectionChoices.SWAP_WORST.value[0]

		self.draft_pick.protection_metadata = metadata
		other_pick.protection_metadata = other_metadata

		other_pick.save()

	@transaction.atomic
	def transfer_asset(self) -> None:
		"""
		Executes the trade by transferring the asset to the receiver.

		Raises:
			ValidationError: If the asset type is unknown.
		"""
		if self.asset_type == "player":
			self.player_contract.team = self.receiver
			self.player_contract.save()

		elif self.asset_type == "pick":
			self._handle_draft_pick_transfer()
			self.draft_pick.save()

		else:
			raise ValidationError("Unknown asset type.")
