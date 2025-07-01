from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User, Team, Player

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'password_confirm']

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
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_admin', 'date_joined']
        read_only_fields = ['id', 'date_joined']

class TeamSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    total_salary = serializers.SerializerMethodField()
    total_players = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ['id', 'name', 'owner', 'owner_username', 'avatar', 'total_salary', 'total_players', 'created_at']
        read_only_fields = ['id', 'created_at', 'total_salary', 'total_players']

    def get_total_salary(self, obj):
        return obj.total_salary()

    def get_total_players(self, obj):
        return obj.total_players()

class PlayerSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source='team.name', read_only=True)

    class Meta:
        model = Player
        fields = ['id', 'name', 'team', 'team_name', 'salary', 'contract_duration', 
                 'primary_position', 'secondary_position', 'is_rfa', 'created_at']
        read_only_fields = ['id', 'created_at']