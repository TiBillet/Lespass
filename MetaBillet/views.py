from django.http import HttpResponseRedirect
from django.shortcuts import render

# Create your views here.
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView


class index(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return HttpResponseRedirect('https://tibillet.org/')
        # return render(request, 'html5up-story/index.html')




