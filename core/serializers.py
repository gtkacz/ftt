from rest_framework import serializers

from ftt.common.util import django_obj_to_dict

from .models import NBATeam, Player, Team, User


class UserRegistrationSerializer(serializers.ModelSerializer):
	password = serializers.CharField(
		write_only=True,
		min_length=8,
		help_text='Password must be at least 8 characters long',
	)
	password_confirm = serializers.CharField(
		write_only=True, help_text='Must match the password field'
	)

	class Meta:
		model = User
		fields = '__all__'
		extra_kwargs = {
			'username': {'help_text': 'Unique username for the user'},
			'email': {'help_text': 'User email address'},
			'first_name': {'help_text': 'User first name'},
			'last_name': {'help_text': 'User last name'},
		}

	def validate(self, attrs):
		if attrs['password'] != attrs['password_confirm']:
			raise serializers.ValidationError("Passwords don't match")
		return attrs

	def create(self, validated_data):
		validated_data.pop('password_confirm')
		password = validated_data.pop('password')
		user = User.objects.create_user(**validated_data)
		user.set_password(password)
		user.save()
		return user


class NBATeamSerializer(serializers.ModelSerializer):
	class Meta:
		model = NBATeam
		fields = '__all__'
		read_only_fields = ['id', 'created_at']
		extra_kwargs = {
			'name': {'help_text': 'NBA team name'},
			'abbreviation': {'help_text': 'NBA team abbreviation (e.g. LAL)'},
			'city': {'help_text': 'City where the NBA team is based'},
			'conference': {'help_text': 'Conference the team belongs to (East/West)'},
			'created_at': {'help_text': 'Date and time when NBA team was added'},
		}


class TeamSerializer(serializers.ModelSerializer):
	owner_username = serializers.CharField(
		source='owner.username', read_only=True, help_text='Username of the team owner'
	)
	total_salary = serializers.SerializerMethodField(
		help_text='Total salary of all players on the team'
	)
	total_players = serializers.SerializerMethodField(
		help_text='Number of players currently on the team'
	)
	available_salary = serializers.SerializerMethodField(
		help_text='Available salary cap after accounting for current team salary'
	)
	available_players = serializers.SerializerMethodField(
		help_text='Number of available player slots based on current roster and league settings'
	)
	can_bid = serializers.SerializerMethodField(
		help_text='Whether the team can bid on players based on current roster and salary cap'
	)

	class Meta:
		model = Team
		fields = '__all__'
		read_only_fields = ['id', 'created_at', 'total_salary', 'total_players']
		extra_kwargs = {
			'name': {'help_text': 'Team name'},
			'owner': {'help_text': 'User ID of the team owner'},
			'avatar': {'help_text': 'Team avatar image (optional)'},
			'created_at': {'help_text': 'Date and time when team was created'},
		}

	def get_total_salary(self, obj: Team) -> float:
		return obj.total_salary()

	def get_total_players(self, obj: Team) -> int:
		return obj.total_players()

	def get_available_salary(self, obj: Team) -> float:
		return obj.available_salary()

	def get_available_players(self, obj: Team) -> int:
		return obj.available_players()

	def get_can_bid(self, obj: Team) -> bool:
		return obj.can_bid()


class UserSerializer(serializers.ModelSerializer):
	team = TeamSerializer(
		read_only=True,
		help_text='Team information for the user, if they own a team',
	)

	class Meta:
		model = User
		fields = '__all__'
		read_only_fields = ['id', 'date_joined']
		extra_kwargs = {
			'username': {'help_text': 'Unique username for the user'},
			'email': {'help_text': 'User email address'},
			'first_name': {'help_text': 'User first name'},
			'last_name': {'help_text': 'User last name'},
			'date_joined': {'help_text': 'Date and time when user joined'},
		}


class PlayerSerializer(serializers.ModelSerializer):
	team_name = serializers.CharField(
		source='team.name',
		read_only=True,
		help_text='Name of the team this player belongs to',
	)
	photo = serializers.SerializerMethodField(
		help_text='URL to the player photo, if available'
	)
	real_team = serializers.SerializerMethodField(
		help_text='Real NBA team this player is associated with, if any'
	)
	relevancy = serializers.SerializerMethodField(
		read_only=True,
		help_text='Relevancy score of the player based on performance metrics',
	)

	def get_real_team(self, obj: Player) -> str:
		if obj.real_team:
			return django_obj_to_dict(obj.real_team)
		return ''

	def get_photo(self, obj: Player) -> str:
		if obj.nba_id:
			return f'https://cdn.nba.com/headshots/nba/latest/1040x760/{obj.nba_id}.png'
		return ''

	def get_relevancy(self, obj: Player) -> float:
		from json import loads

		if not obj.metadata:
			return 0.0
		try:
			metadata = loads(obj.metadata)
			return (
				metadata.get('PTS', 0.0)
				+ metadata.get('AST', 0.0)
				+ metadata.get('REB', 0.0)
			)
		except (ValueError, TypeError):
			return 0.0

	class Meta:
		model = Player
		fields = '__all__'
		read_only_fields = ['id', 'created_at']
		extra_kwargs = {
			'name': {'help_text': 'Player full name'},
			'team': {
				'help_text': 'Team ID this player belongs to (can be null for free agents)'
			},
			'salary': {'help_text': 'Player annual salary in dollars'},
			'contract_duration': {'help_text': 'Contract length in years (1-10)'},
			'primary_position': {
				'help_text': 'Primary position: G (Guard), F (Forward), or C (Center)'
			},
			'secondary_position': {
				'help_text': 'Secondary position (optional): G, F, or C'
			},
			'is_rfa': {'help_text': 'Whether player is a Restricted Free Agent'},
			'created_at': {'help_text': 'Date and time when player was added'},
		}
