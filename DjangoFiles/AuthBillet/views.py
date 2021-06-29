from django.shortcuts import render

# Create your views here.
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class activate(APIView):
    permission_classes = [AllowAny]

    def get(self, uid, token):
        print(uid, token)

        return Response(f'{uid} {token}', status=status.HTTP_200_OK)