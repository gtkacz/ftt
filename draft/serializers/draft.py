from rest_framework import serializers

from core.serializers import SimplePlayerSerializer
from draft.models import Draft
from draft.serializers.draft_pick import DraftPositionSerializer


class DraftSerializer(serializers.ModelSerializer):
	draftable_players = SimplePlayerSerializer(
		many=True,
		read_only=True,
		help_text="List of all players available in this draft",
	)
	draft_positions = DraftPositionSerializer(
		many=True, read_only=True, help_text="Complete draft order and pick status",
	)

	class Meta:
		model = Draft
		fields = "__all__"
		read_only_fields = ["id", "created_at"]
