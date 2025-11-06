from rest_framework.exceptions import ValidationError
from rest_framework.serializers import ModelSerializer, SerializerMethodField

from core.serializers import SimplePlayerSerializer, TeamSerializer
from draft.serializers.pick import PickSerializer
from trade.models import Trade
from trade.types.assets import Asset


class TradeSerializer(ModelSerializer):
	sender = TeamSerializer(read_only=True)
	participants = TeamSerializer(many=True, read_only=True)
	assets = SerializerMethodField()

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
		assets = {
			"players": [],
			"picks": [],
			"other_assets": [],
		}

		for asset in obj.assets.all():
			if asset.asset_type == "player" and asset.player is not None:
				serialized_player = SimplePlayerSerializer(asset.player).data
				assets["players"].append(serialized_player)

			elif asset.asset_type == "pick" and asset.pick is not None:
				serialized_pick = PickSerializer(asset.pick).data
				assets["picks"].append(serialized_pick)

			raise ValidationError(f"Unknown asset type: {asset.asset_type}")

		return assets

	class Meta:  # noqa: D106
		model = Trade
		fields = "__all__"
