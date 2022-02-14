from rest_framework import serializers
from AuthBillet.models import TibilletUser
import logging
logger = logging.getLogger(__name__)



class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TibilletUser
        fields = [
            'email',
            'first_name',
            'last_name',
            'phone',
            'accept_newsletter',
            'postal_code',
            'birth_date',
            'can_create_tenant',
            'espece',
            'is_staff',
        ]
        read_only_fields = fields