from rest_framework import serializers

from core.serializers import PlayerSerializer

from .models import Draft, DraftPosition, Pick


class PickSerializer(serializers.ModelSerializer):
	original_team_name = serializers.CharField(
		source='original_team.name', read_only=True
	)
	current_team_name = serializers.CharField(
		source='current_team.name', read_only=True
	)

	class Meta:
		model = Pick
		fields = [
			'id',
			'original_team',
			'original_team_name',
			'current_team',
			'current_team_name',
			'draft_year',
			'round_number',
			'protections',
			'created_at',
		]
		read_only_fields = ['id', 'created_at']


class DraftPositionSerializer(serializers.ModelSerializer):
	team_name = serializers.CharField(source='team.name', read_only=True)
	selected_player_name = serializers.CharField(
		source='selected_player.name', read_only=True
	)

	class Meta:
		model = DraftPosition
		fields = [
			'id',
			'team',
			'team_name',
			'round_number',
			'pick_number',
			'overall_pick',
			'selected_player',
			'selected_player_name',
			'is_pick_made',
			'pick_made_at',
		]
		read_only_fields = ['id', 'pick_made_at']


class DraftSerializer(serializers.ModelSerializer):
	draftable_players = PlayerSerializer(many=True, read_only=True)
	draft_positions = DraftPositionSerializer(many=True, read_only=True)

	class Meta:
		model = Draft
		fields = [
			'id',
			'year',
			'draftable_players',
			'draft_positions',
			'is_completed',
			'is_snake_draft',
			'created_at',
		]
		read_only_fields = ['id', 'created_at']
