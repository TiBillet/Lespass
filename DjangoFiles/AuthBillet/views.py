from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.shortcuts import render

# Create your views here.
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from djoser.views import UserViewSet, TokenCreateView
import requests
from django.db import connection
from django.utils.translation import ugettext_lazy as _

from AuthBillet.models import TibilletUser
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


@permission_classes([permissions.AllowAny])
class create_user(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        if not email :
            return Response("email required", status=status.HTTP_400_BAD_REQUEST)
        else :
            email = email.lower()

        User: TibilletUser = get_user_model()
        user, created = User.objects.get_or_create(email=email, username=email)

        if not created :
            if user.is_active :
                return Response(_("email de connection envoyé. Verifiez vos spam si non reçu."), status=status.HTTP_202_ACCEPTED)
            else :
                return Response("Not Active", status=status.HTTP_401_UNAUTHORIZED)
        else :
            if password:
                user.set_password(password)

            user.is_active = False

            user.espece = TibilletUser.TYPE_HUM
            user.client_achat.add(connection.tenant)
            user.save()
            return Response('User Créé, merci de valider votre adresse email.', status=status.HTTP_201_CREATED)

