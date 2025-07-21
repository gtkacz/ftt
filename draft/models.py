from datetime import datetime, time, timedelta
from random import shuffle
from zoneinfo import ZoneInfo

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

	def current_player_pool(self) -> models.QuerySet[Player]:
		"""Returns the list of players still available for drafting"""
		return self.draftable_players.filter(contract__isnull=True)

	def drafted_players(self) -> models.QuerySet[Player]:
		"""Returns the list of players that have been drafted in this draft"""
		return self.draftable_players.filter(contract__isnull=False)

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
						is_current=(overall_pick == 1),
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
	is_current = models.BooleanField(default=False)
	is_auto_pick = models.BooleanField(default=False)
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
		if not self.started_at or not self.is_current:
			return self.draft.time_limit_per_pick * 60  # Convert minutes to seconds

		# Calculate when the pick deadline will be
		deadline = self._calculate_pick_deadline(
			self.started_at, self.draft.time_limit_per_pick
		)

		# Return seconds between now and the deadline
		now = timezone.now()
		if now >= deadline:
			return 0

		return round((deadline - now).total_seconds())

	def can_pick_until(self) -> datetime:
		"""Calculates the datetime until which the pick can be made"""
		if not self.started_at or not self.is_current:
			return timezone.now() + timedelta(minutes=self.draft.time_limit_per_pick)

		return self._calculate_pick_deadline(
			self.started_at, self.draft.time_limit_per_pick
		)

	def _calculate_pick_deadline(
		self, start_time: datetime, limit_minutes: int
	) -> datetime:
		"""Calculate when the pick deadline will be, accounting for active hours"""
		lower_bound = self.draft.pick_hour_lower_bound
		upper_bound = self.draft.pick_hour_upper_bound
		app_timezone = ZoneInfo(str(timezone.get_current_timezone()))

		remaining_seconds = limit_minutes * 60
		current_time = start_time

		while remaining_seconds > 0:
			current_date = current_time.date()

			# Create the active window for current date using app timezone
			window_start = datetime.combine(current_date, time(lower_bound, 0))
			window_start = window_start.astimezone(app_timezone)

			window_end = datetime.combine(current_date, time(upper_bound, 0))
			window_end = window_end.astimezone(app_timezone)

			# If we're before the window, jump to window start
			if current_time < window_start:
				current_time = window_start
			# If we're after the window, jump to next day's window start
			elif current_time >= window_end:
				next_date = current_date + timedelta(days=1)
				next_window_start = datetime.combine(next_date, time(lower_bound, 0))
				current_time = next_window_start.astimezone(app_timezone)
				continue

			# Calculate how much time we can use in this window
			time_until_window_end = (window_end - current_time).total_seconds()

			if remaining_seconds <= time_until_window_end:
				# We can finish within this window
				return current_time + timedelta(seconds=remaining_seconds)
			else:
				# Use up this window and continue to next day
				remaining_seconds -= time_until_window_end
				next_date = current_date + timedelta(days=1)
				next_window_start = datetime.combine(next_date, time(lower_bound, 0))
				current_time = next_window_start.astimezone(app_timezone)

		return current_time

	def remaining_seconds(self) -> int:
		"""Calculates the time left for the current pick in seconds"""
		if not self.started_at or not self.is_current:
			return self.draft.time_limit_per_pick * 60  # Convert minutes to seconds

		now = timezone.now()
		total_limit_seconds = self.draft.time_limit_per_pick * 60
		elapsed_active_seconds = self._get_elapsed_active_seconds(self.started_at, now)

		return max(0, total_limit_seconds - elapsed_active_seconds)

	def _get_elapsed_active_seconds(
		self, start_time: datetime, end_time: datetime
	) -> int:
		"""Calculate active seconds elapsed between start_time and end_time"""
		if start_time >= end_time:
			return 0

		lower_bound = self.draft.pick_hour_lower_bound
		upper_bound = self.draft.pick_hour_upper_bound
		app_timezone = ZoneInfo(str(timezone.get_current_timezone()))

		total_seconds = 0
		current_date = start_time.date()

		while current_date <= end_time.date():
			# Create the active window for this date using app timezone
			window_start = datetime.combine(current_date, time(lower_bound, 0))
			window_start = window_start.astimezone(app_timezone)

			window_end = datetime.combine(current_date, time(upper_bound, 0))
			window_end = window_end.astimezone(app_timezone)

			# Find intersection with our time range
			range_start = max(start_time, window_start)
			range_end = min(end_time, window_end)

			if range_start < range_end:
				total_seconds += (range_end - range_start).total_seconds()

			current_date += timedelta(days=1)

		return round(total_seconds)

	def make_pick(self, player: Player | None) -> Player:
		"""Make a pick for the draft position"""
		if self.time_left_to_pick() <= 0:
			from json import loads

			self.is_auto_pick = True

			players = (
				self.draft.current_player_pool()
				.filter(real_team__isnull=False)
				.values('id', 'metadata')
			)
			players = [
				{**loads(player['metadata']), 'id': player['id']} for player in players
			]

			_player = max(
				players,
				key=lambda p: p.get('PTS', 0) + p.get('REB', 0) + p.get('AST', 0),
			)
			player = Player.objects.get(id=_player['id'])

			print(f'Auto-picking player {player.nba_id} for pick {self.overall_pick}')

		if not player or not self.contract or not self.pick or not self.draft:
			raise ValueError('Invalid pick')

		if self.is_pick_made:
			raise ValueError('Pick has already been made')

		if not self.draft.current_player_pool().filter(id=player.id).exists():
			raise ValueError('Player is not available for drafting')

		if not self.is_current:
			raise ValueError('Draft pick is not current')

		next_pick = self.draft.draft_positions.filter(
			overall_pick=self.overall_pick + 1
		).first()

		with transaction.atomic():
			self.selected_player = player
			self.is_pick_made = True
			self.pick_made_at = timezone.now()
			self.is_current = False

			self.contract.player = player
			self.contract.team = self.pick.current_team

			self.draft.draftable_players.remove(player)

			self.save()
			self.contract.save()
			self.draft.save()

			if next_pick:
				next_pick.is_current = True
				next_pick.started_at = timezone.now()
				next_pick.save()

		return self.selected_player

	class Meta:
		ordering = ['draft', 'pick']
		unique_together = ['draft', 'pick']
		constraints = [
			models.UniqueConstraint(
				fields=['draft'],
				condition=models.Q(is_current=1),
				name='only_one_current_pick_per_draft',
			)
		]
