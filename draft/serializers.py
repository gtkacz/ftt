from rest_framework import serializers
from .models import Pick, Draft
from core.serializers import PlayerSerializer

class PickSerializer(serializers.ModelSerializer):
    original_team_name = serializers.CharField(source='original_team.name', read_only=True)
    current_team_name = serializers.CharField(source='current_team.name', read_only=True)

    class Meta:
        model = Pick
        fields = ['id', 'original_team', 'original_team_name', 'current_team', 
                 'current_team_name', 'draft_year', 'round_number', 'protections', 'created_at']
        read_only_fields = ['id', 'created_at']

class DraftSerializer(serializers.ModelSerializer):
    draftable_players = PlayerSerializer(many=True, read_only=True)
    draft_order = PickSerializer(many=True, read_only=True)

    class Meta:
        model = Draft
        fields = ['id', 'year', 'draftable_players', 'draft_order', 'is_completed', 'created_at']
        read_only_fields = ['id', 'created_at']