from rest_framework import serializers
from userprofiles.models import EPassportNumber, UserProfile
from staff_dashboard.serializers import UserProfileSerializer

class EpassportNumberSerializer(serializers.ModelSerializer):
    user_profile = UserProfileSerializer()
    class Meta:
        model = EPassportNumber
        #fields = "__all__"
        exclude = ['id',
                   'created_at', 
                   'updated_at', 
                   'created_by', 
                   'updated_by', 
                   'alphabet', 
                   'number']


class UserProfileApiRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        exclude = ['user']
