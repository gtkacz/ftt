from django.db import models

from core.models import Player, Team


class Pick(models.Model):
	"""Represents draft capital/assets that teams own"""

	original_team = models.ForeignKey(
		Team, on_delete=models.CASCADE, related_name='original_picks'
	)
	current_team = models.ForeignKey(
		Team, on_delete=models.CASCADE, related_name='current_picks'
	)
	draft_year = models.PositiveIntegerField()
	round_number = models.PositiveIntegerField()
	protections = models.TextField(
		null=True, blank=True, help_text='Description of pick protections'
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'{self.draft_year} Round {self.round_number} - {self.current_team.name}'

	class Meta:
		ordering = ['draft_year', 'round_number']
		unique_together = ['original_team', 'draft_year', 'round_number']


class Draft(models.Model):
	"""Represents a draft event"""

	year = models.PositiveIntegerField(unique=True)
	draftable_players = models.ManyToManyField(
		Player, related_name='drafts', blank=True
	)
	is_completed = models.BooleanField(default=False)
	is_snake_draft = models.BooleanField(
		default=True, help_text='Snake draft reverses order each round'
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'{self.year} Draft'

	class Meta:
		ordering = ['-year']


class DraftPosition(models.Model):
	"""Represents the actual picking order in a draft"""

	draft = models.ForeignKey(
		Draft, on_delete=models.CASCADE, related_name='draft_positions'
	)
	team = models.ForeignKey(Team, on_delete=models.CASCADE)
	round_number = models.PositiveIntegerField()
	pick_number = models.PositiveIntegerField(help_text='Pick number within the round')
	overall_pick = models.PositiveIntegerField(help_text='Overall pick number in draft')
	selected_player = models.ForeignKey(
		Player, on_delete=models.SET_NULL, null=True, blank=True
	)
	is_pick_made = models.BooleanField(default=False)
	pick_made_at = models.DateTimeField(null=True, blank=True)

	def __str__(self):
		return f'{self.draft.year} Draft - Round {self.round_number}, Pick {self.pick_number} ({self.team.name})'

	class Meta:
		ordering = ['draft', 'overall_pick']
		unique_together = ['draft', 'overall_pick']
