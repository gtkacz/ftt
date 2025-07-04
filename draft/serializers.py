from rest_framework import serializers

from core.serializers import PlayerSerializer

from .models import Draft, DraftPosition, Pick


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
		extra_kwargs = {
			'original_team': {'help_text': 'Team ID that originally owned this pick'},
			'current_team': {'help_text': 'Team ID that currently owns this pick'},
			'draft_year': {'help_text': 'Year this pick can be used in the draft'},
			'round_number': {'help_text': 'Round number of this pick (1, 2, etc.)'},
			'protections': {
				'help_text': 'Optional description of pick protections (e.g., "Top 3 protected")'
			},
			'created_at': {'help_text': 'Date and time when pick was created'},
		}


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
		extra_kwargs = {
			'team': {'help_text': 'Team ID making this pick'},
			'round_number': {'help_text': 'Round number (1, 2, etc.)'},
			'pick_number': {'help_text': 'Pick number within the round'},
			'overall_pick': {'help_text': 'Overall pick number in the entire draft'},
			'selected_player': {
				'help_text': 'Player ID selected with this pick (if made)'
			},
			'is_pick_made': {'help_text': 'Whether this pick has been made yet'},
			'pick_made_at': {'help_text': 'Date and time when pick was made'},
		}


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
		extra_kwargs = {
			'year': {'help_text': 'Draft year (must be unique)'},
			'is_completed': {'help_text': 'Whether this draft has been completed'},
			'is_snake_draft': {
				'help_text': 'Whether this is a snake draft (reverses order each round)'
			},
			'created_at': {'help_text': 'Date and time when draft was created'},
		}
