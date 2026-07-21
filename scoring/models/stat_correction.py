from django.db import models


class StatCorrection(models.Model):
	"""An observed post-settlement stat diff; applied only while the scoring period was open."""

	line = models.ForeignKey("scoring.PlayerGameLine", on_delete=models.CASCADE, related_name="corrections")
	field = models.CharField(max_length=20)
	old_value = models.FloatField()
	new_value = models.FloatField()
	applied = models.BooleanField(default=False)
	detected_at = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"{self.line}: {self.field} {self.old_value} -> {self.new_value}"
