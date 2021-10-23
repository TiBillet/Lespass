from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.shortcuts import render

# Create your views here.
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from djoser.views import UserViewSet, TokenCreateView
import requests
from django.db import connection
from TiBillet import settings
from djoser.conf import settings as djoser_settings

from djoser import utils
User = get_user_model()

class TokenCreateView_custom(TokenCreateView):
    """
    Use this endpoint to obtain user authentication token.
    """

    serializer_class = djoser_settings.SERIALIZERS.token_create
    permission_classes = djoser_settings.PERMISSIONS.token_create

    def _action(self, serializer):
        token = utils.login_user(self.request, serializer.user)
        token_serializer_class = djoser_settings.SERIALIZERS.token

        # on modifie la creation du token pour rajouter access_token dans la réponse pour Postman
        data_response = token_serializer_class(token).data
        data_response['access_token'] = data_response.get('auth_token')
        # import ipdb; ipdb.set_trace()
        print(f'data_response {data_response}')
        return Response(
                data=data_response, status=status.HTTP_200_OK
            )

class activate(APIView):
    permission_classes = [AllowAny]


    def get(self, request, uid, token):
        print(uid)
        print(token)

        # import ipdb; ipdb.set_trace()
        user = User.objects.get(pk=utils.decode_uid(uid))

        PR = PasswordResetTokenGenerator()
        is_token_valid = PR.check_token( user, token )

        # if is_token_valid :
            #TODO POUR DEMAIN JOJO : DEMANDER LE MOT DE PASSE ICI !

        domain = self.request.tenant.domain_url
        protocol = "https"

        if settings.DEBUG :
            domain += ":8002"
            protocol = "http"

        post_url = f"{protocol}://{domain}/auth/users/activation/"
        post_data = {"uid": uid, "token": token}
        result = requests.post(post_url, data=post_data)
        content = result.text

        return Response(f'{uid} {token} {result.text} {result.status_code}')

