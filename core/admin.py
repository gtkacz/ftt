from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Team, Player

class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('is_admin',)}),
    )
    list_display = BaseUserAdmin.list_display + ('is_admin',)

class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'total_salary', 'total_players', 'created_at']
    search_fields = ['name', 'owner__username']

class PlayerAdmin(admin.ModelAdmin):
    list_display = ['name', 'team', 'salary', 'contract_duration', 'primary_position', 'is_rfa']
    list_filter = ['primary_position', 'secondary_position', 'is_rfa', 'team']
    search_fields = ['name', 'team__name']

admin.site.register(User, UserAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(Player, PlayerAdmin)