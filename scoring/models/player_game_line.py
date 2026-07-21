from django.db import models


class PlayerGameLine(models.Model):
	"""A player's raw stat line for one game plus the derived fantasy points."""

	player = models.ForeignKey("core.Player", on_delete=models.CASCADE, related_name="game_lines")
	game = models.ForeignKey("scoring.NbaGame", on_delete=models.CASCADE, related_name="lines")
	raw_stats = models.JSONField(default=dict)
	fpts = models.DecimalField(max_digits=8, decimal_places=2, default=0)
	is_final = models.BooleanField(default=False)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = (models.UniqueConstraint(fields=("player", "game"), name="unique_line_per_player_game"),)

	def __str__(self) -> str:
		return f"{self.player} @ {self.game_id}: {self.fpts}"
