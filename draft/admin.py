from django.contrib import admin
from .models import Pick, Draft

class PickAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'original_team', 'current_team', 'draft_year', 'round_number']
    list_filter = ['draft_year', 'round_number']
    search_fields = ['original_team__name', 'current_team__name']

class DraftAdmin(admin.ModelAdmin):
    list_display = ['year', 'is_completed', 'created_at']
    filter_horizontal = ['draftable_players', 'draft_order']

admin.site.register(Pick, PickAdmin)
admin.site.register(Draft, DraftAdmin)