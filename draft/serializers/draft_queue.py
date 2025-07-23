from rest_framework import serializers

from core.models import Player
from core.serializers import SimplePlayerSerializer
from draft.models import DraftQueue


class DraftQueueSerializer(serializers.ModelSerializer):
	queue_items = serializers.SerializerMethodField(
		help_text='List of players in the draft queue'
	)
	team_name = serializers.CharField(source='team.name', read_only=True)
	draft_year = serializers.IntegerField(source='draft.year', read_only=True)

	def get_queue_items(self, obj):
		"""Return a list of player IDs in the draft queue"""
		return (
			[
				SimplePlayerSerializer(Player.objects.get(id=item)).data
				for item in obj.queue_items
			]
			if obj.queue_items
			else []
		)

	class Meta:
		model = DraftQueue
		fields = '__all__'


class ReorderQueueSerializer(serializers.Serializer):
	player_ids = serializers.ListField(
		child=serializers.IntegerField(),
		help_text='List of player IDs in desired order',
	)

	def validate_player_ids(self, value):
		from core.models import Player

		if not Player.objects.filter(id__in=value).exists():
			raise serializers.ValidationError('One or more players do not exist')

		return value
