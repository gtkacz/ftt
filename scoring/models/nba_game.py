from django.db import models


class NbaGame(models.Model):
	"""One real NBA game tracked from ESPN."""

	STATUS_SCHEDULED = "scheduled"
	STATUS_LIVE = "live"
	STATUS_FINAL = "final"
	STATUS_SETTLED = "settled"
	STATUS_CHOICES = (
		(STATUS_SCHEDULED, "Scheduled"),
		(STATUS_LIVE, "Live"),
		(STATUS_FINAL, "Final (box not yet stable)"),
		(STATUS_SETTLED, "Settled"),
	)

	espn_event_id = models.CharField(max_length=20, unique=True)
	starts_at = models.DateTimeField()
	home = models.ForeignKey("core.NBATeam", on_delete=models.SET_NULL, null=True, related_name="home_games")
	away = models.ForeignKey("core.NBATeam", on_delete=models.SET_NULL, null=True, related_name="away_games")
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
	period = models.PositiveSmallIntegerField(default=0)
	clock = models.CharField(max_length=10, blank=True)
	settle_hash = models.CharField(
		max_length=64,
		blank=True,
		help_text="SHA-256 of the last fetched box, for stability detection",
	)
	scoring_period = models.ForeignKey(
		"scoring.ScoringPeriod",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="games",
	)

	class Meta:
		ordering = ("starts_at",)

	def __str__(self) -> str:
		return f"{self.away} @ {self.home} ({self.espn_event_id})"
