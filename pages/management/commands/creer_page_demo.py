"""
Cree une page d'accueil de demonstration avec un bloc de chaque type.
/ Creates a demo home page with one block of each type.

LOCALISATION : pages/management/commands/creer_page_demo.py

But : tester visuellement le rendu de la racine "/" par l'app pages, avec tous
les types de blocs. Idempotent : on recree la page et ses blocs a chaque appel.
/ Goal: visually test the rendering of the root "/" by the pages app, with all
block types. Idempotent: the page and its blocks are recreated on each call.

Usage :
    python manage.py creer_page_demo            # tenant "lespass" par defaut
    python manage.py creer_page_demo --schema=mon_tenant
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from Customers.models import Client
from pages.models import Bloc, Page


class Command(BaseCommand):
    help = "Cree une page d'accueil de demonstration (tous les types de blocs)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            default="lespass",
            help="Nom du schema tenant ou creer la page (defaut : lespass).",
        )

    def handle(self, *args, **options):
        schema = options["schema"]

        # On recupere le tenant et on se place dans son schema.
        # / Get the tenant and switch into its schema.
        try:
            tenant = Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            self.stderr.write(f"Tenant introuvable : {schema}")
            return

        with tenant_context(tenant):
            self._creer_page_demo()
            self.stdout.write(
                f"Page de demonstration creee/mise a jour sur le tenant '{schema}'. "
                f"Visible sur la racine /"
            )

    def _creer_page_demo(self):
        # Page d'accueil de demonstration (slug "accueil-demo").
        # / Demo home page (slug "accueil-demo").
        page, _cree = Page.objects.get_or_create(
            slug="accueil-demo",
            defaults={"titre": "Accueil (démo)", "position": 0},
        )
        page.titre = "Accueil (démo)"
        page.publie = True
        page.est_accueil = True
        page.meta_description = "Page de démonstration de l'app pages TiBillet."
        page.save()

        # On repart d'une page propre : on supprime les blocs existants.
        # / Start from a clean page: delete existing blocks.
        page.blocs.all().delete()

        # 1 — HERO
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.HERO,
            position=1,
            titre="Bienvenue à Lespass",
            sous_titre="Un lieu culturel, sa programmation et ses adhésions, "
            "réunis sur une page composée de blocs.",
            bouton_label="Voir l'agenda",
            bouton_url="/event/",
            bouton2_label="Adhérer",
            bouton2_url="/memberships/",
        )

        # 2 — PARAGRAPHE
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.PARAGRAPHE,
            position=2,
            titre="Notre lieu",
            texte=(
                "<p>Ce paragraphe riche est édité avec l'éditeur de texte de "
                "l'administration. On peut y mettre du <strong>gras</strong>, de "
                "l'<em>italique</em> et des listes.</p>"
                "<ul><li>Concerts et spectacles</li>"
                "<li>Ateliers et résidences</li>"
                "<li>Espace de convivialité</li></ul>"
            ),
        )

        # 3 — IMAGE + TEXTE (sans image pour la demo : ajout possible via l'admin)
        # / IMAGE + TEXT (no image in the demo: can be added via the admin)
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.IMAGE_TEXTE,
            position=3,
            titre="Image et texte",
            texte=(
                "<p>Ce bloc associe une image et un texte, l'image pouvant être "
                "placée à gauche ou à droite. Ajoutez une image depuis "
                "l'administration pour voir la mise en page complète.</p>"
            ),
            image_position=Bloc.DROITE,
            bouton_label="En savoir plus",
            bouton_url="/event/",
        )

        # 4 — CTA
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.CTA,
            position=4,
            titre="Envie de nous rejoindre ?",
            sous_titre="Prenez une adhésion et soutenez le lieu toute l'année.",
            bouton_label="Devenir adhérent·e",
            bouton_url="/memberships/",
            bouton2_label="Nous contacter",
            bouton2_url="/infos-pratiques/",
        )

        # 5 — TEMOIGNAGE
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.TEMOIGNAGE,
            position=5,
            texte="<p>Un lieu chaleureux et une équipe accueillante. "
            "On s'y sent tout de suite chez soi.</p>",
            auteur_nom="Camille D.",
            auteur_role="adhérente",
        )
