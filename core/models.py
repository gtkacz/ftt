from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class User(AbstractUser):
	is_admin = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.username


class Team(models.Model):
	name = models.CharField(max_length=100)
	owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name='team')
	avatar = models.ImageField(upload_to='team_avatars/', null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name

	def total_salary(self):
		return sum(player.salary for player in self.players.all())

	def total_players(self):
		return self.players.count()


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
		max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
	)
	contract_duration = models.PositiveIntegerField(
		validators=[MinValueValidator(1), MaxValueValidator(10)]
	)
	primary_position = models.CharField(max_length=1, choices=POSITION_CHOICES)
	secondary_position = models.CharField(
		max_length=1, choices=POSITION_CHOICES, null=True, blank=True
	)
	is_rfa = models.BooleanField(default=False, help_text='Restricted Free Agent')
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name

	class Meta:
		ordering = ['name']
