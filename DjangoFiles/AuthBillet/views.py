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

class activate(APIView):
    permission_classes = [AllowAny]


    def get(self, request, uid, token):
        print(uid)
        print(token)

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

