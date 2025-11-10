from collections.abc import Sequence
from typing import Any

from django.db import models

from core.models.notification import Notification
from ftt.settings import LEAGUE_SETTINGS


class Team(models.Model):
	"""Model representing a basketball team."""

	name = models.CharField(max_length=100)
	owner = models.OneToOneField("core.User", on_delete=models.CASCADE, related_name="team")
	# avatar = models.ImageField(upload_to='team_avatars/', null=True, blank=True, default='team_avatars/logo.png')  # noqa: ERA001
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return self.name

	def save(self, *args: Sequence[Any], **kwargs: dict[str, Any]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride] # noqa: D102
		if not self.id:  # pyright: ignore[reportAttributeAccessIssue]
			# Create a notification for the owner when the team is created
			Notification.objects.create(
				user=self.owner,
				message=f'Your team "{self.name}" has been created.',
				priority=1,
				level="info",
			)

		else:
			if self.available_salary() < 0:
				Notification.objects.create(
					user=self.owner,
					message=f'Your team "{self.name}" has hit the salary cap.',
					priority=1,
					level="warning",
				)

			if self.available_players() < 0:
				Notification.objects.create(
					user=self.owner,
					message=f'Your team "{self.name}" has hit the player cap.',
					priority=1,
					level="warning",
				)

		return super().save(*args, **kwargs)  # pyright: ignore[reportArgumentType]

	@property
	def players(self) -> models.QuerySet["Player"]:  # noqa: F821
		"""Return all players associated with this team."""
		from core.models.player import Player

		return Player.objects.filter(contract__team=self)

	def total_salary(self) -> float:
		"""Calculate the total salary of all players on the team."""  # noqa: DOC201
		return sum(player.contract.salary for player in self.players.filter(is_ir=False))

	def total_players(self) -> int:
		"""Count the total number of active players on the team."""  # noqa: DOC201
		return self.players.filter(is_ir=False).count()

	def available_salary(self) -> float:
		"""Calculate the available salary cap for the team."""  # noqa: DOC201
		return LEAGUE_SETTINGS.SALARY_CAP - self.total_salary()

	def available_players(self) -> int:
		"""Calculate the available player slots for the team."""  # noqa: DOC201
		return LEAGUE_SETTINGS.MAX_PLAYER_CAP - self.total_players()

	def can_bid(self) -> bool:
		"""Check if the team can place a bid based on salary and player cap."""  # noqa: DOC201
		return (
			self.total_players() < LEAGUE_SETTINGS.MAX_PLAYER_CAP and self.total_salary() < LEAGUE_SETTINGS.SALARY_CAP
		)
