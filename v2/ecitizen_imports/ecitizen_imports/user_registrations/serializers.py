from django.core.validators import MinLengthValidator
from rest_framework import serializers


class UserRegistrationSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    spiritual_name = serializers.CharField(required=False)
    gender = serializers.CharField(required=True)
    email = serializers.EmailField(label="Email", required=True)
    password = serializers.CharField(validators=[MinLengthValidator(8)], required=True)
    country_code = serializers.CharField(required=True)
    phone_number = serializers.CharField(
        required=True,
    )
    zone_code = serializers.CharField(
        required=True,
    )
