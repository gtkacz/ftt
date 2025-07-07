from django.contrib import admin

from .models import Draft, DraftPosition, Pick


class PickAdmin(admin.ModelAdmin):
	list_display = [
		'__str__',
		'original_team',
		'current_team',
		'draft_year',
		'round_number',
	]
	list_filter = ['draft_year', 'round_number']
	search_fields = ['original_team__name', 'current_team__name']


class DraftPositionInline(admin.TabularInline):
	model = DraftPosition
	extra = 0
	readonly_fields = ['pick_made_at']


class DraftAdmin(admin.ModelAdmin):
	list_display = ['year', 'is_completed', 'created_at']
	filter_horizontal = ['draftable_players']
	inlines = [DraftPositionInline]


class DraftPositionAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'team', 'selected_player', 'is_pick_made']
	list_filter = ['draft__year', 'round_number', 'is_pick_made']
	search_fields = ['team__name', 'selected_player__name']
	readonly_fields = ['pick_made_at']


admin.site.register(Pick, PickAdmin)
admin.site.register(Draft, DraftAdmin)
admin.site.register(DraftPosition, DraftPositionAdmin)
