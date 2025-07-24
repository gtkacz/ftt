from django.db import migrations


def data_migration(apps, schema_editor):
	NBATeam = apps.get_model("core", "NBATeam")

	data = [
		{"city": "Portland", "name": "Trail Blazers", "abbreviation": "POR"},
		{"city": "Houston", "name": "Rockets", "abbreviation": "HOU"},
		{"city": "Los Angeles", "name": "Lakers", "abbreviation": "LAL"},
		{"city": "Denver", "name": "Nuggets", "abbreviation": "DEN"},
		{"city": "Sacramento", "name": "Kings", "abbreviation": "SAC"},
		{"city": "Memphis", "name": "Grizzlies", "abbreviation": "MEM"},
		{"city": "Golden State", "name": "Warriors", "abbreviation": "GSW"},
		{"city": "Philadelphia", "name": "76ers", "abbreviation": "PHI"},
		{"city": "Pittsburgh", "name": "Ironmen", "abbreviation": "PIT"},
		{"city": "Oklahoma City", "name": "Thunder", "abbreviation": "OKC"},
		{"city": "New York", "name": "Knicks", "abbreviation": "NYK"},
		{"city": "LA", "name": "Clippers", "abbreviation": "LAC"},
		{"city": "Orlando", "name": "Magic", "abbreviation": "ORL"},
		{"city": "Phoenix", "name": "Suns", "abbreviation": "PHX"},
		{"city": "Detroit", "name": "Pistons", "abbreviation": "DET"},
		{"city": "Brooklyn", "name": "Nets", "abbreviation": "BKN"},
		{"city": "Atlanta", "name": "Hawks", "abbreviation": "ATL"},
		{"city": "Miami", "name": "Heat", "abbreviation": "MIA"},
		{"city": "Cleveland", "name": "Cavaliers", "abbreviation": "CLE"},
		{"city": "Charlotte", "name": "Hornets", "abbreviation": "CHA"},
		{"city": "Toronto", "name": "Raptors", "abbreviation": "TOR"},
		{"city": "Dallas", "name": "Mavericks", "abbreviation": "DAL"},
		{"city": "Boston", "name": "Celtics", "abbreviation": "BOS"},
		{"city": "New Orleans", "name": "Pelicans", "abbreviation": "NOP"},
		{"city": "Washington", "name": "Wizards", "abbreviation": "WAS"},
		{"city": "San Antonio", "name": "Spurs", "abbreviation": "SAS"},
		{"city": "Milwaukee", "name": "Bucks", "abbreviation": "MIL"},
		{"city": "Chicago", "name": "Bulls", "abbreviation": "CHI"},
		{"city": "Indiana", "name": "Pacers", "abbreviation": "IND"},
		{"city": "Utah", "name": "Jazz", "abbreviation": "UTA"},
		{"city": "Baltimore", "name": "Bullets", "abbreviation": "BAL"},
		{"city": "Detroit", "name": "Falcons", "abbreviation": "DEF"},
		{"city": "Minnesota", "name": "Timberwolves", "abbreviation": "MIN"},
		{"city": "Chicago", "name": "Stags", "abbreviation": "CHS"},
		{"city": "St. Louis", "name": "Bombers", "abbreviation": "BOM"},
		{"city": "Indianapolis", "name": "Olympians", "abbreviation": "INO"},
		{"city": "Cleveland", "name": "Rebels", "abbreviation": "CLR"},
		{"city": "Providence", "name": "Steamrollers", "abbreviation": "PRO"},
		{"city": "Toronto", "name": "Huskies", "abbreviation": "HUS"},
		{"city": "Waterloo", "name": "Hawks", "abbreviation": "WAT"},
		{"city": "Indianapolis", "name": "Jets", "abbreviation": "JET"},
		{"city": "Denver", "name": "Nuggets", "abbreviation": "DN "},
		{"city": "Sheboygan", "name": "Redskins", "abbreviation": "SHE"},
		{"city": "Anderson", "name": "Packers", "abbreviation": "AND"},
	]

	for datum in data:
		NBATeam.objects.update_or_create(**datum)


class Migration(migrations.Migration):
	dependencies = [
		("core", "0013_team_datamigration"),
	]

	operations = [
		migrations.RunPython(data_migration, atomic=True),
	]
