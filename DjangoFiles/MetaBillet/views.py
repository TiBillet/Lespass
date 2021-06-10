from django.shortcuts import render

# Create your views here.
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView


class index(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return render(request, 'massively/index.html')