from random import shuffle

from django.db import models, transaction
from django.utils import timezone

from core.models import Contract, Player, Team


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
	is_from_league_draft = models.BooleanField(
		default=False, help_text='Indicates if this pick is from a league draft'
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

	year = models.PositiveIntegerField()
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

	def generate_draft_order(self) -> list[int]:
		"""Generates a snake draft order based on the list of teams"""
		teams = list(self.teams.all().values_list('id', flat=True))

		teams_order = list(teams)
		shuffle(teams_order)

		return teams_order

	def start(self):
		"""Starts the draft and generates the draft order"""
		if self.is_completed:
			raise ValueError('Draft is already completed')

		if not self.teams.exists():
			raise ValueError('Draft must have at least one team')

		if not self.draftable_players.exists():
			raise ValueError('Draft must have at least one draftable player')

		with transaction.atomic():
			teams_order = self.generate_draft_order()
			picks = (
				Pick.objects.none()
				if self.is_league_draft
				else Pick.objects.filter(draft_year=self.year)
			)

			DraftPick.objects.filter(draft=self).delete()

			overall_pick = 1

			for round_num in range(1, self.rounds + 1):
				pick_order = teams_order if round_num % 2 == 1 else teams_order[::-1]

				for pick_num, team_id in enumerate(pick_order, 1):
					current_pick = (
						Pick.objects.create(
							original_team_id=team_id,
							current_team_id=team_id,
							draft_year=self.year,
							round_number=round_num,
							is_from_league_draft=True,
						)
						if self.is_league_draft
						else picks.filter(
							current_team_id=team_id,
							round_number=round_num,
							is_from_league_draft=False,
						).first()
					)

					draft_pick = DraftPick.objects.create(
						draft=self,
						pick=current_pick,
						pick_number=pick_num,
						overall_pick=overall_pick,
					)

					current_contract = draft_pick.generate_contract()
					draft_pick.contract = current_contract
					draft_pick.save()

					overall_pick += 1

			self.save()

			return teams_order

	def __str__(self):
		return f'{self.year} Draft'

	class Meta:
		ordering = ['-year']
		unique_together = ['year', 'is_league_draft']


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
	contract = models.OneToOneField(
		Contract,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='draft_pick',
		help_text='Contract associated with the drafted player',
	)

	def __str__(self):
		return f'{self.draft.year} Draft - Round {self.pick.round_number}, Pick {self.pick_number} ({self.pick.current_team.name})'

	def generate_contract(self) -> Contract:
		if not self.pick or not self.pick_number or not self.pick.round_number:
			raise ValueError(
				'Pick number and round number must be set to generate a contract'
			)

		data = {}

		if self.draft.is_league_draft:
			if self.pick.round_number == 1:
				data = {
					'duration': 2,
					'salary': 25,
				}

			elif self.pick.round_number == 2:
				data = {
					'duration': 2,
					'salary': 20,
				}

			elif self.pick.round_number == 3:
				data = {
					'duration': 2,
					'salary': 15,
				}

			elif self.pick.round_number == 4:
				data = {
					'duration': 2,
					'salary': 12,
				}

			elif self.pick.round_number == 5:
				data = {
					'duration': 2,
					'salary': 8.5,
				}

			elif self.pick.round_number == 6:
				data = {
					'duration': 1,
					'salary': 8.5,
					'is_to': True,
				}

			elif self.pick.round_number == 7:
				data = {
					'duration': 1,
					'salary': 7.5,
					'is_to': True,
				}

			elif self.pick.round_number == 8:
				data = {
					'duration': 1,
					'salary': 5,
					'is_to': True,
				}

			elif self.pick.round_number == 9:
				data = {
					'duration': 1,
					'salary': 5,
					'is_to': True,
				}

			elif self.pick.round_number == 10:
				data = {
					'duration': 1,
					'salary': 5,
					'is_to': True,
				}

			elif self.pick.round_number == 11:
				data = {
					'duration': 2,
					'salary': 3.5,
				}

			elif self.pick.round_number == 12:
				data = {
					'duration': 2,
					'salary': 3.5,
				}

			elif self.pick.round_number == 13:
				data = {
					'duration': 2,
					'salary': 3.5,
				}

			elif self.pick.round_number == 14:
				data = {
					'duration': 2,
					'salary': 2,
				}

			else:
				data = {
					'duration': 2,
					'salary': 2,
				}

		return Contract.objects.create(
			player=self.selected_player,
			team=self.pick.current_team,
			start_year=self.draft.year,
			**data,
		)

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
