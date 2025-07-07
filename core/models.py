from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from ftt.settings import LEAGUE_SETTINGS


class User(AbstractUser):
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	is_approved = models.BooleanField(
		default=False, help_text='User is approved to participate in the league'
	)

	def __str__(self):
		return self.username


class Notification(models.Model):
	user = models.ForeignKey(
		User, on_delete=models.CASCADE, related_name='notifications'
	)
	message = models.CharField(max_length=255)
	is_read = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'Notification for {self.user.username}: {self.message}'


class Team(models.Model):
	name = models.CharField(max_length=100)
	owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name='team')
	avatar = models.ImageField(upload_to='team_avatars/', null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name

	def total_salary(self) -> float:
		return sum(player.salary for player in self.players.all())

	def total_players(self) -> int:
		return self.players.count()

	def available_salary(self) -> float:
		return LEAGUE_SETTINGS.SALARY_CAP - self.total_salary()

	def available_players(self) -> int:
		return LEAGUE_SETTINGS.MAX_PLAYER_CAP - self.total_players()

	def can_bid(self) -> bool:
		return (
			self.total_players() < LEAGUE_SETTINGS.MAX_PLAYER_CAP
			and self.total_salary() < LEAGUE_SETTINGS.SALARY_CAP
		)


class Player(models.Model):
	POSITION_CHOICES = [
		('G', 'Guard'),
		('F', 'Forward'),
		('C', 'Center'),
	]

	name = models.CharField(max_length=100)
	team = models.ForeignKey(
		Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='players'
	)
	salary = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		validators=[MinValueValidator(0)],
		null=True,
		blank=True,
	)
	contract_duration = models.PositiveIntegerField(
		validators=[MinValueValidator(1), MaxValueValidator(10)], null=True, blank=True
	)
	primary_position = models.CharField(max_length=1, choices=POSITION_CHOICES)
	secondary_position = models.CharField(
		max_length=1, choices=POSITION_CHOICES, null=True, blank=True
	)
	nba_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
	is_rfa = models.BooleanField(default=False, help_text='Restricted Free Agent')
	is_to = models.BooleanField(default=False, help_text='Team Option')
	is_ir = models.BooleanField(default=False, help_text='Injury Reserve')
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name

	class Meta:
		ordering = ['name']
