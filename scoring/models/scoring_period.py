from datetime import datetime

from django.db import models


class ScoringPeriod(models.Model):
	"""One matchup week (Mon-Sun). Corrections apply only while the period is open."""

	index = models.PositiveIntegerField(unique=True)
	starts_at = models.DateTimeField()
	ends_at = models.DateTimeField()
	is_closed = models.BooleanField(default=False)

	class Meta:
		ordering = ("index",)

	def __str__(self) -> str:
		return f"Week {self.index}"

	@classmethod
	def for_datetime(cls, dt: datetime) -> "ScoringPeriod | None":
		"""Return the period containing ``dt``, if any."""
		return cls.objects.filter(starts_at__lte=dt, ends_at__gt=dt).first()
