from rest_framework import serializers

from core.serializers import PlayerSerializer

from .models import Draft, DraftPick, Pick


class PickSerializer(serializers.ModelSerializer):
	original_team_name = serializers.CharField(
		source='original_team.name',
		read_only=True,
		help_text='Name of the team that originally owned this pick',
	)
	current_team_name = serializers.CharField(
		source='current_team.name',
		read_only=True,
		help_text='Name of the team that currently owns this pick',
	)

	class Meta:
		model = Pick
		fields = '__all__'
		read_only_fields = ['id', 'created_at']


class DraftPositionSerializer(serializers.ModelSerializer):
	team_name = serializers.CharField(
		source='team.name',
		read_only=True,
		help_text='Name of the team making this pick',
	)
	selected_player_name = serializers.CharField(
		source='selected_player.name',
		read_only=True,
		help_text='Name of the selected player (if pick has been made)',
	)

	class Meta:
		model = DraftPick
		fields = '__all__'
		read_only_fields = ['id', 'pick_made_at']


class DraftSerializer(serializers.ModelSerializer):
	draftable_players = PlayerSerializer(
		many=True,
		read_only=True,
		help_text='List of all players available in this draft',
	)
	draft_positions = DraftPositionSerializer(
		many=True, read_only=True, help_text='Complete draft order and pick status'
	)

	class Meta:
		model = Draft
		fields = '__all__'
		read_only_fields = ['id', 'created_at']
