from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import Player, Team, User


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
		fields = [
			'username',
			'email',
			'first_name',
			'last_name',
			'password',
			'password_confirm',
		]
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


class UserSerializer(serializers.ModelSerializer):
	class Meta:
		model = User
		fields = [
			'id',
			'username',
			'email',
			'first_name',
			'last_name',
			'is_admin',
			'date_joined',
		]
		read_only_fields = ['id', 'date_joined']
		extra_kwargs = {
			'username': {'help_text': 'Unique username for the user'},
			'email': {'help_text': 'User email address'},
			'first_name': {'help_text': 'User first name'},
			'last_name': {'help_text': 'User last name'},
			'is_admin': {'help_text': 'Whether the user has admin privileges'},
			'date_joined': {'help_text': 'Date and time when user joined'},
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

	class Meta:
		model = Team
		fields = [
			'id',
			'name',
			'owner',
			'owner_username',
			'avatar',
			'total_salary',
			'total_players',
			'created_at',
		]
		read_only_fields = ['id', 'created_at', 'total_salary', 'total_players']
		extra_kwargs = {
			'name': {'help_text': 'Team name'},
			'owner': {'help_text': 'User ID of the team owner'},
			'avatar': {'help_text': 'Team avatar image (optional)'},
			'created_at': {'help_text': 'Date and time when team was created'},
		}

	def get_total_salary(self, obj):
		return obj.total_salary()

	def get_total_players(self, obj):
		return obj.total_players()


class PlayerSerializer(serializers.ModelSerializer):
	team_name = serializers.CharField(
		source='team.name',
		read_only=True,
		help_text='Name of the team this player belongs to',
	)

	class Meta:
		model = Player
		fields = [
			'id',
			'name',
			'team',
			'team_name',
			'salary',
			'contract_duration',
			'primary_position',
			'secondary_position',
			'is_rfa',
			'created_at',
		]
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
