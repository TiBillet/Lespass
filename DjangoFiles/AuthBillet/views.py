from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.shortcuts import render

# Create your views here.
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from djoser.views import UserViewSet
import requests
from django.db import connection
from TiBillet import settings
from djoser import utils
User = get_user_model()

class activate(APIView):
    permission_classes = [AllowAny]


    def get(self, request, uid, token):
        print(uid)
        print(token)

        import ipdb; ipdb.set_trace()
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

