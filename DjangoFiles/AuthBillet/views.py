import json
import logging

import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db.utils import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import render

# Create your views here.
from rest_framework import status, permissions, viewsets, serializers
from rest_framework.decorators import permission_classes
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import connection
from django.utils.translation import ugettext_lazy as _
# from rest_framework_api_key.models import APIKey
from rest_framework_api_key.models import APIKey
from rest_framework_api_key.permissions import HasAPIKey
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.views import TokenViewBase, TokenRefreshView

from ApiBillet.views import request_for_data_cashless
from AuthBillet.models import TibilletUser, TenantAdminPermission, TermUser
from rest_framework_simplejwt.tokens import RefreshToken

from AuthBillet.serializers import MeSerializer, CreateUserValidator, CreateTerminalValidator, TokenTerminalValidator
from AuthBillet.utils import get_or_create_user, sender_mail_connect, get_client_ip
from BaseBillet.models import Configuration, ApiKey

from django.utils.encoding import force_str, force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from TiBillet import settings

User = get_user_model()
logger = logging.getLogger(__name__)

from authlib.integrations.base_client import OAuthError
from authlib.integrations.django_client import OAuth
from authlib.oauth2.rfc6749 import OAuth2Token
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

oauth = OAuth()
sso_client = oauth.register(
    **settings.OAUTH_CLIENT,
)


def encode_uid(pk):
    return force_str(urlsafe_base64_encode(force_bytes(pk)))


def decode_uid(pk):
    return force_str(urlsafe_base64_decode(pk))


'''
from djoser.conf import settings as djoser_settings
from djoser import utils
from djoser.views import UserViewSet, TokenCreateView
EX DJOSER MODEL
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
'''


class TokenRefreshViewCustom(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        super_return = super().post(request, *args, **kwargs)
        '''
        Surclassage de la fonction Refresh
        On s'assure ici que le refresh token d'un terminal provient
        bien de lui avec sa mac_adress et son unique_id
        '''
        # import ipdb; ipdb.set_trace()
        serializer = self.get_serializer(data=request.data)
        refresh = serializer.token_class(self.request.data.get('refresh'))
        # user = TibilletUser.objects.get(pk=refresh['user_id'])
        user = get_object_or_404(TibilletUser, pk=refresh['user_id'])

        if user.espece == TibilletUser.TYPE_TERM:
            try:
                assert user.mac_adress_sended == request.data.get('mac_adress')
                assert user.terminal_uuid == request.data.get('unique_id')
            except AssertionError as e:
                refresh.blacklist()
                raise AuthenticationFailed(
                    f"AssertionError",
                )

        return super_return


'''
class create_api_key(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, requests):
        pass
'''



class test_api_key(APIView):
    '''
    exemple :
    curl -H "Authorization: Api-Key HzwiP9dA.dz8Qic6P6MamtTv9yd8KGTUaxoGNH0tn" -X GET https://demo.betabillet.tech/user/keytest/
    '''
    permission_classes = [HasAPIKey]

    def get(self, request):
        key = request.META["HTTP_AUTHORIZATION"].split()[1]
        api_key = APIKey.objects.get_from_key(key)
        tenant_apikey = get_object_or_404(ApiKey, key=api_key)
        ip = get_client_ip(request)


        data = {
            "auth": tenant_apikey.auth,
            "ip_request": ip,
            "ip_valid": ip == tenant_apikey.ip
        }

        return Response(
            data,
            status=status.HTTP_200_OK,
        )



class activate(APIView):
    permission_classes = [AllowAny]

    def get(self, request, uid, token):
        user = User.objects.get(pk=decode_uid(uid))
        if user.email_error:
            return Response('Mail non valide', status=status.HTTP_406_NOT_ACCEPTABLE)

        PR = PasswordResetTokenGenerator()
        is_token_valid = PR.check_token(user, token)
        # print(user)
        if is_token_valid:
            user.is_active = True
            refresh = RefreshToken.for_user(user)
            user.save()
            data = {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
            return Response(data, status=status.HTTP_200_OK)

        else:
            return Response('Token non valide', status=status.HTTP_400_BAD_REQUEST)


class create_user(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        validator = CreateUserValidator(data=request.data)
        if not validator.is_valid():
            return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

        email = validator.validated_data.get('email').lower()
        password = validator.validated_data.get('password')

        user = get_or_create_user(email, password, send_mail=False)

        if user:
            sender_mail_connect(user.email)
            return Response(_('Pour acceder à votre espace et réservations, '
                              'merci de valider votre adresse email. '
                              'Pensez à regarder dans les spams !'),
                            status=status.HTTP_200_OK)
        else:
            return Response(_("Email soumis non valide. "
                              "Merci de vérifier votre adresse."),
                            status=status.HTTP_406_NOT_ACCEPTABLE)


class create_terminal_user(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logger.info(f"create_terminal_user request.data : {request.data}")
        validator = CreateTerminalValidator(data=request.data)
        if not validator.is_valid():
            return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

        logger.info(f"create_terminal_user validated_data : {validator.data}")
        return Response(validator.data, status=status.HTTP_200_OK)


class validate_token_terminal(APIView):
    permission_classes = [AllowAny]

    def post(self, request, token):
        logger.info(f"validate_token_terminal : {token}")
        validator = TokenTerminalValidator(data=request.data, context={'request': request, 'token': token})
        if not validator.is_valid():
            return Response(validator.errors, status=status.HTTP_400_BAD_REQUEST)

        logger.info(f"validate_token_terminal validated_data : {validator.data}")
        return Response(validator.data, status=status.HTTP_200_OK)


class MeViewset(viewsets.ViewSet):

    def list(self, request):
        serializer = MeSerializer(request.user)
        serializer_copy = serializer.data.copy()

        configuration = Configuration.get_solo()
        if configuration.server_cashless and configuration.key_cashless:
            serializer_copy['cashless'] = request_for_data_cashless(request.user)

        return Response(serializer_copy, status=status.HTTP_200_OK)

    def get_permissions(self):
        if self.action in ['list', ]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]


class OAauthApi(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        communecter = oauth.create_client('communecter')
        redirect_uri = request.build_absolute_uri('/api/user/oauth').replace('http://', 'https://')
        logger.info(f"redirect_uri : {redirect_uri}")

        auth = communecter.authorize_redirect(request, redirect_uri)
        if type(auth) == HttpResponseRedirect:
            if auth.status_code == 302:
                return auth
        else:
            return Response('SSO "Communecter" non disponible. Essayez avec votre email',
                            status=status.HTTP_404_NOT_FOUND)


class OAauthCallback(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        token = oauth.communecter.authorize_access_token(request)

        if token.get('access_token'):
            user_info = oauth.communecter.get('/oauth/userinfo', token=token).json()
            if user_info.get('email_verified'):

                user = get_or_create_user(
                    user_info.get('email'),
                    set_active=True,
                    send_mail=False,
                )

                uid = encode_uid(user.pk)
                token = default_token_generator.make_token(user)
                redirect_uri = request.build_absolute_uri(f'/emailconfirmation/{uid}/{token}') \
                    .replace('http://', 'https://')
                return HttpResponseRedirect(redirect_uri)


            else:
                get_or_create_user(user_info.get('email'))
                redirect_uri = request.build_absolute_uri().replace('http://', 'https://')
                return HttpResponseRedirect(redirect_uri)

        else:
            return Response('Access not Ok', status=status.HTTP_401_UNAUTHORIZED)
