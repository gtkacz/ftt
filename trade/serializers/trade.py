from rest_framework.exceptions import ValidationError
from rest_framework.serializers import ModelSerializer, SerializerMethodField

from core.serializers import SimplePlayerSerializer, TeamSerializer
from draft.serializers.pick import PickSerializer
from trade.models import Trade
from trade.types.assets import Asset


class TradeSerializer(ModelSerializer):  # noqa: D101
	sender = TeamSerializer()
	participants = TeamSerializer(many=True)
	assets = SerializerMethodField()
	status = SerializerMethodField()

	@staticmethod
	def get_assets(obj: Trade) -> Asset:
		"""
		Get the assets involved in the trade, categorized by type.

		Args:
			obj (Trade): The trade instance.

		Raises:
			ValidationError: If an unknown asset type is encountered.

		Returns:
			Asset: A dictionary with asset types as keys and lists of serialized assets as values.
		"""
		assets: Asset = {
			"players": [],
			"picks": [],
		}

		if isinstance(obj, dict):
			return assets

		for asset in obj.assets.all():
			if asset.asset_type == "player" and asset.player_contract is not None:
				serialized_player = SimplePlayerSerializer(asset.player_contract).data
				assets["players"].append(serialized_player)
				continue

			if asset.asset_type == "pick" and asset.draft_pick is not None:
				serialized_pick = PickSerializer(asset.draft_pick).data
				assets["picks"].append(serialized_pick)
				continue

			raise ValidationError(f"Unknown asset type: {asset.asset_type}")

		return assets

	@staticmethod
	def get_status(obj: Trade) -> dict[str, dict[int, str]]:
		"""
		Get the current overall status of the trade.

		Args:
			obj (Trade): The trade instance.

		Returns:
			dict[str, dict[int, str]]: The current status code of the trade.
		"""
		return {"participants": obj.participant_statuses, "commissioners": obj.commissioner_statuses}

	class Meta:  # noqa: D106
		model = Trade
		fields = "__all__"
