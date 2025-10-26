from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings

from rest_framework import viewsets, permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response

from fedow_public.models import AssetFedowPublic
from .models import Initiative, Contribution
from django.contrib.auth import get_user_model

User = get_user_model()

def demo_data():
    if settings.DEBUG:
        if not Initiative.objects.all():
            project1 = Initiative.objects.create(
                name="Demo Project",
                description="This is a demo project",
                funding_goal=1000,
                asset=AssetFedowPublic.objects.get(category=AssetFedowPublic.STRIPE_FED_FIAT),
            )

            Contribution.objects.create(
                initiative=project1,
                contributor=User.objects.get(email="jturbeaux@pm.me"),
                amount=100,
            )

            project2 = Initiative.objects.create(
                name="Demo Project 2",
                description="This is a demo project 2",
                funding_goal=10000,
                asset=AssetFedowPublic.objects.get(category=AssetFedowPublic.STRIPE_FED_FIAT),
            )
            Contribution.objects.create(
                initiative=project2,
                contributor=User.objects.get(email="jturbeaux@pm.me"),
                amount=1500,
            )

# Create your views here.
class InitiativeViewSet(viewsets.ViewSet):
    """
    ViewSet affichant les projets à financer et gérant les contributions.
    Compatible avec HTMX et Stripe.
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.AllowAny]

    # ------------------------
    # Liste des projets
    # ------------------------
    def list(self, request):
        """
        Affiche la liste des projets avec Bootstrap + HTMX.
        """
        if settings.DEBUG:
            demo_data()

        initiatives = Initiative.objects.all().order_by("-created_at")
        context = {
            "initiatives": initiatives,
        }
        return render(request, "initiatives_list.html", context)


    # ------------------------
    # Détail d’un projet
    # ------------------------
    def retrieve(self, request, pk=None):
        """
        Affiche le détail d’un projet (vue modale ou page dédiée).
        """
        initiative = get_object_or_404(Initiative, pk=pk)
        return render(request, "initiative_detail.html", context={"initiative": initiative})

