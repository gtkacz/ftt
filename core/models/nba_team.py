from django.db import models


class NBATeam(models.Model):
	"""Model representing an NBA team."""

	city = models.CharField(max_length=100)
	name = models.CharField(max_length=100)
	abbreviation = models.CharField(max_length=3, unique=True)

	def __str__(self) -> str:
		return f"{self.city} {self.name} ({self.abbreviation})"
