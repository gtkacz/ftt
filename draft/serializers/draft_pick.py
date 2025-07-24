from rest_framework import serializers

from draft.models import DraftPick


class DraftPositionSerializer(serializers.ModelSerializer):
	team_name = serializers.CharField(
		source="team.name",
		read_only=True,
		help_text="Name of the team making this pick",
	)
	selected_player_name = serializers.CharField(
		source="selected_player.name",
		read_only=True,
		help_text="Name of the selected player (if pick has been made)",
	)

	class Meta:
		model = DraftPick
		fields = "__all__"
		read_only_fields = ["id", "pick_made_at"]
