from rest_framework import serializers

from draft.serializers.pick import PickSerializer
from ftt.common.util import django_obj_to_dict

from .models import Contract, NBATeam, Notification, Player, Team, User


class UserRegistrationSerializer(serializers.ModelSerializer):
	password = serializers.CharField(
		write_only=True,
		min_length=8,
		help_text="Password must be at least 8 characters long",
	)
	password_confirm = serializers.CharField(write_only=True, help_text="Must match the password field")

	class Meta:
		model = User
		fields = "__all__"

	def validate(self, attrs):
		if attrs["password"] != attrs["password_confirm"]:
			raise serializers.ValidationError("Passwords don't match")
		return attrs

	def create(self, validated_data):
		validated_data.pop("password_confirm")
		password = validated_data.pop("password")
		user = User.objects.create_user(**validated_data)
		user.set_password(password)
		user.save()
		return user


class UserUpdateSerializer(serializers.ModelSerializer):
	password = serializers.CharField(
		write_only=True,
		min_length=8,
		help_text="Password must be at least 8 characters long",
	)
	password_confirm = serializers.CharField(write_only=True, help_text="Must match the password field")

	class Meta:
		model = User
		fields = "__all__"

	def validate(self, attrs):
		if attrs["password"] != attrs["password_confirm"]:
			raise serializers.ValidationError("Passwords don't match")
		return attrs

	def update(self, instance, validated_data):
		validated_data.pop("password_confirm", None)
		password = validated_data.pop("password", None)

		for attr, value in validated_data.items():
			setattr(instance, attr, value)

		if password:
			instance.set_password(password)

		instance.save()
		return instance


class NBATeamSerializer(serializers.ModelSerializer):
	class Meta:
		model = NBATeam
		fields = "__all__"
		read_only_fields = ["id", "created_at"]


class TeamSerializer(serializers.ModelSerializer):
	owner_username = serializers.CharField(
		source="owner.username", read_only=True, help_text="Username of the team owner",
	)
	total_salary = serializers.SerializerMethodField(help_text="Total salary of all players on the team")
	total_players = serializers.SerializerMethodField(help_text="Number of players currently on the team")
	available_salary = serializers.SerializerMethodField(
		help_text="Available salary cap after accounting for current team salary",
	)
	available_players = serializers.SerializerMethodField(
		help_text="Number of available player slots based on current roster and league settings",
	)
	can_bid = serializers.SerializerMethodField(
		help_text="Whether the team can bid on players based on current roster and salary cap",
	)
	players = serializers.SerializerMethodField(
		help_text="List of players currently on the team",
	)
	current_picks = PickSerializer(
		many=True,
		read_only=True,
		help_text="List of draft picks owned by the team",
	)

	class Meta:
		model = Team
		fields = "__all__"
		read_only_fields = ["id", "created_at", "total_salary", "total_players"]

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

	def get_players(self, obj: Team) -> list:
		return SimplePlayerSerializer(obj.players.all(), many=True).data


class UserSerializer(serializers.ModelSerializer):
	team = TeamSerializer(
		read_only=True,
		help_text="Team information for the user, if they own a team",
	)

	class Meta:
		model = User
		fields = "__all__"
		read_only_fields = ["id", "date_joined"]


class ContractSerializer(serializers.ModelSerializer):
	team = TeamSerializer(
		read_only=True,
		help_text="Team information for the contract, if applicable",
	)

	class Meta:
		model = Contract
		fields = "__all__"
		read_only_fields = ["id", "created_at", "team"]


class SimplePlayerSerializer(serializers.ModelSerializer):
	team_name = serializers.CharField(
		source="team.name",
		read_only=True,
		help_text="Name of the team this player belongs to",
	)
	photo = serializers.SerializerMethodField(help_text="URL to the player photo, if available")
	real_team = serializers.SerializerMethodField(help_text="Real NBA team this player is associated with, if any")
	relevancy = serializers.SerializerMethodField(
		read_only=True,
		help_text="Relevancy score of the player based on performance metrics",
	)
	contract = serializers.SerializerMethodField(
		read_only=True,
		help_text="Contract information for the player, if they are part of a team",
	)
	team = serializers.SerializerMethodField(
		read_only=True,
		help_text="Team information for the player, if they are part of a team",
	)

	def get_contract(self, obj: Player) -> dict:
		if hasattr(obj, "contract"):
			return django_obj_to_dict(obj.contract, exclude_fields=["team"])

		return {}

	def get_team(self, obj: Player) -> dict:
		if hasattr(obj, "contract"):
			return django_obj_to_dict(obj.contract.team, exclude_fields=["players", "current_picks"])

		return {}

	def get_real_team(self, obj: Player) -> str:
		if obj.real_team:
			return django_obj_to_dict(obj.real_team)
		return ""

	def get_photo(self, obj: Player) -> str:
		if obj.nba_id:
			return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{obj.nba_id}.png"
		return ""

	def get_relevancy(self, obj: Player) -> float:
		try:
			from json import loads

			if (
				not obj
				or not obj.metadata
				or not isinstance(obj.metadata, str)
				or not obj.metadata.strip()
				or obj.metadata == "null"
			):
				return 0.0

			metadata = loads(obj.metadata.lower().replace("nan", "null"))

			return round(
				float(metadata.get("fpts", 0.0))
				or (float(metadata.get("pts", 0.0)) + float(metadata.get("ast", 0.0)) + float(metadata.get("reb", 0.0)))
				/ 2.0,
				1,
			)
		except Exception:
			return 0.0

	class Meta:
		model = Player
		fields = "__all__"
		read_only_fields = ["id", "created_at"]


class PlayerSerializer(SimplePlayerSerializer):
	team_name = serializers.CharField(
		source="team.name",
		read_only=True,
		help_text="Name of the team this player belongs to",
	)
	photo = serializers.SerializerMethodField(help_text="URL to the player photo, if available")
	real_team = serializers.SerializerMethodField(help_text="Real NBA team this player is associated with, if any")
	relevancy = serializers.SerializerMethodField(
		read_only=True,
		help_text="Relevancy score of the player based on performance metrics",
	)
	contract = serializers.SerializerMethodField(
		read_only=True,
		help_text="Contract information for the player, if they are part of a team",
	)
	team = serializers.SerializerMethodField(
		read_only=True,
		help_text="Team information for the player, if they are part of a team",
	)

	def get_contract(self, obj: Player) -> dict:
		if hasattr(obj, "contract"):
			return ContractSerializer(obj.contract).data

		return {}

	def get_team(self, obj: Player) -> dict:
		if hasattr(obj, "contract"):
			return TeamSerializer(obj.contract.team).data

		return {}

	def get_real_team(self, obj: Player) -> str:
		if obj.real_team:
			return django_obj_to_dict(obj.real_team)
		return ""

	def get_photo(self, obj: Player) -> str:
		if obj.nba_id:
			return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{obj.nba_id}.png"
		return ""

	def get_relevancy(self, obj: Player) -> float:
		try:
			from json import loads

			if (
				not obj
				or not obj.metadata
				or not isinstance(obj.metadata, str)
				or not obj.metadata.strip()
				or obj.metadata == "null"
			):
				return 0.0

			metadata = loads(obj.metadata.lower().replace("nan", "null"))

			return round(
				float(metadata.get("fpts", 0.0))
				or (
					float(metadata.get("pts", 0.0)) + float(metadata.get("ast", 0.0)) + float(metadata.get("reb", 0.0))
				),
				1,
			)
		except Exception:
			return 0.0

	class Meta:
		model = Player
		fields = "__all__"
		read_only_fields = ["id", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
	class Meta:
		model = Notification
		fields = "__all__"
		read_only_fields = ["id", "created_at", "updated_at"]
		extra_kwargs = {
			"user": {"required": False, "allow_null": True},
			"read": {"default": False},
		}
