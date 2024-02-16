from rest_framework import serializers


class LoginEmailValidator(serializers.Serializer):
    email = serializers.EmailField()