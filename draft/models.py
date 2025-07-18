from django.db import models
from django.utils import timezone

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
	protections = models.TextField(
		null=True, blank=True, help_text='Description of pick protections'
	)
	round_number = models.PositiveIntegerField()
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
	is_league_draft = models.BooleanField(default=False)
	teams = models.ManyToManyField(
		Team,
		related_name='drafts',
		blank=True,
		help_text='Teams participating in the draft',
	)
	rounds = models.PositiveIntegerField(
		default=2, help_text='Number of rounds in the draft'
	)
	starts_at = models.DateTimeField(
		null=True, blank=True, help_text='Start time of the draft'
	)
	time_limit_per_pick = models.PositiveIntegerField(
		default=180, help_text='Time limit in minutes for each pick'
	)
	pick_hour_lower_bound = models.PositiveIntegerField(
		default=8,
		help_text='Lower bound for the hour of the day when picks can be made',
	)
	pick_hour_upper_bound = models.PositiveIntegerField(
		default=22,
		help_text='Upper bound for the hour of the day when picks can be made',
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def current_player_pool(self) -> models.QuerySet:
		"""Returns the list of players still available for drafting"""
		return self.draftable_players.filter(
			is_active=True, contract__isnull=True
		).order_by('name')

	def drafted_players(self) -> models.QuerySet:
		"""Returns the list of players that have been drafted in this draft"""
		return self.draftable_players.filter(contract__isnull=False).order_by('name')

	@classmethod
	def generate_snake_order(cls, teams: list[Team]) -> list[Team]:
		"""Generates a snake draft order based on the list of teams"""
		order = []

		for i in range(len(teams)):
			if i % 2 == 0:
				order.append(teams[i])
			else:
				order.append(teams[len(teams) - 1 - i])

		return order

	def __str__(self):
		return f'{self.year} Draft'

	class Meta:
		ordering = ['-year']


class DraftPick(models.Model):
	"""Represents the actual picking order in a draft"""

	draft = models.ForeignKey(
		Draft, on_delete=models.CASCADE, related_name='draft_positions'
	)
	pick = models.ForeignKey(
		Pick,
		on_delete=models.CASCADE,
		related_name='draft_positions',
		null=True,
		blank=True,
	)
	pick_number = models.PositiveIntegerField(help_text='Pick number within the round')
	overall_pick = models.PositiveIntegerField(help_text='Overall pick number in draft')
	selected_player = models.ForeignKey(
		Player, on_delete=models.SET_NULL, null=True, blank=True
	)
	started_at = models.DateTimeField(
		null=True, blank=True, help_text='Time when the pick was started'
	)
	is_pick_made = models.BooleanField(default=False)
	pick_made_at = models.DateTimeField(null=True, blank=True)

	def __str__(self):
		return f'{self.draft.year} Draft - Round {self.pick__round_number}, Pick {self.pick_number} ({self.team.name})'

	def time_left_to_pick(self) -> int:
		"""Calculates the time left for the current pick in seconds"""
		if not self.started_at:
			return self.draft.time_limit_per_pick * 60  # Convert minutes to seconds
		
		now = timezone.now()
		total_limit_seconds = self.draft.time_limit_per_pick * 60
		elapsed_active_seconds = self._get_elapsed_active_seconds(self.started_at, now)
		
		return max(0, total_limit_seconds - elapsed_active_seconds)

	def _get_elapsed_active_seconds(self, start_time, end_time):
		"""Calculate active seconds elapsed between start_time and end_time"""
		from datetime import datetime, time, timedelta
		
		if start_time >= end_time:
			return 0
		
		lower_bound = self.draft.pick_hour_lower_bound
		upper_bound = self.draft.pick_hour_upper_bound
		
		total_seconds = 0
		current_date = start_time.date()
		
		while current_date <= end_time.date():
			# Create the active window for this date
			window_start = timezone.make_aware(
				datetime.combine(current_date, time(lower_bound, 0))
			)
			window_end = timezone.make_aware(
				datetime.combine(current_date, time(upper_bound, 0))
			)
			
			# Find intersection with our time range
			range_start = max(start_time, window_start)
			range_end = min(end_time, window_end)
			
			if range_start < range_end:
				total_seconds += (range_end - range_start).total_seconds()
			
			current_date += timedelta(days=1)
		
		return total_seconds

	class Meta:
		ordering = ['draft', 'pick']
		unique_together = ['draft', 'pick']
