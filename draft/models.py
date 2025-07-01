from django.db import models
from core.models import Team, Player

class Pick(models.Model):
    original_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='original_picks')
    current_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='current_picks')
    draft_year = models.PositiveIntegerField()
    round_number = models.PositiveIntegerField()
    protections = models.TextField(null=True, blank=True, help_text="Description of pick protections")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.draft_year} Round {self.round_number} - {self.current_team.name}"

    class Meta:
        ordering = ['draft_year', 'round_number']
        unique_together = ['original_team', 'draft_year', 'round_number']

class Draft(models.Model):
    year = models.PositiveIntegerField(unique=True)
    draftable_players = models.ManyToManyField(Player, related_name='drafts', blank=True)
    draft_order = models.ManyToManyField(Pick, related_name='drafts', blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.year} Draft"

    class Meta:
        ordering = ['-year']