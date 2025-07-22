from django.db import migrations


def data_migration(apps, schema_editor):
	Team = apps.get_model('core', 'Team')
	Pick = apps.get_model('draft', 'Pick')

	for year in range(2026, 2028):
		for team in Team.objects.all():
			for r in range(1, 3):
				Pick.objects.get_or_create(
					draft_year=year,
					original_team=team,
					current_team=team,
					round_number=r,
				)


class Migration(migrations.Migration):
	dependencies = [
		('core', '0020_remove_team_avatar'),
		('draft', '0013_draftpick_is_auto_pick'),
	]

	operations = [
		migrations.RunPython(data_migration, atomic=True),
	]
