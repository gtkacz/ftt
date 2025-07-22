from rest_framework import serializers

from draft.models import Pick


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
