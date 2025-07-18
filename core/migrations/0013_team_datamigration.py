from django.db import migrations


def data_migration(apps, schema_editor):
	User = apps.get_model('core', 'User')
	Team = apps.get_model('core', 'Team')

	data = [
		{'name': 'The Meme Team', 'owner': 'gtkacz', 'avatar': ''},
		{'name': 'Extremoz Horse', 'owner': 'adriano.andrade', 'avatar': ''},
		{'name': 'Lukólicos BC', 'owner': 'lucas.sodre', 'avatar': ''},
		{'name': 'Santos Sempre Santos', 'owner': 'airton.ferreira', 'avatar': ''},
		{'name': 'Gigante da Baviera', 'owner': 'arthur.wippel', 'avatar': ''},
		{'name': 'Mãe do Nassir Little', 'owner': 'cesar.castro', 'avatar': ''},
		{'name': 'Blizzards', 'owner': 'fabio.henrique', 'avatar': ''},
		{'name': 'Otaku FC', 'owner': 'felipe.murakoshi', 'avatar': ''},
		{'name': 'Knáticos', 'owner': 'gabriel.cardoso', 'avatar': ''},
		{'name': 'Dynasty Squad', 'owner': 'gian.bachstein', 'avatar': ''},
		{'name': 'Perdi a Casa na bet365', 'owner': 'guilherme.bender', 'avatar': ''},
		{'name': 'Olá Viva', 'owner': 'jeferson.costa', 'avatar': ''},
		{'name': 'Antitank Team', 'owner': 'lucas.cunha', 'avatar': ''},
		{'name': 'Kowalinhas United', 'owner': 'matheus.pacheco', 'avatar': ''},
		{'name': 'Halleluka', 'owner': 'pedro.alencar', 'avatar': ''},
		{'name': 'Aquidauana Cows', 'owner': 'rafael.esbizero', 'avatar': ''},
		{'name': 'Olsheytors', 'owner': 'roberto.almeida', 'avatar': ''},
		{'name': 'Team Cena', 'owner': 'vitor.gutterres', 'avatar': ''},
	]

	for datum in data:
		curr_user = User.objects.get(username=datum['owner'])
		Team.objects.update_or_create(
			name=datum['name'], owner=curr_user, avatar=datum['avatar']
		)


class Migration(migrations.Migration):
	dependencies = [
		('core', '0012_user_datamigration'),
	]

	operations = [
		migrations.RunPython(data_migration, atomic=True),
	]
