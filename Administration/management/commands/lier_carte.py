"""
Lie une carte cashless (NFC) au compte d'un utilisateur, chez Fedow ET dans Lespass.
/ Links a cashless (NFC) card to a user account, on Fedow AND in Lespass.

LOCALISATION : BaseBillet/management/commands/lier_carte.py

A quoi ca sert : en developpement, on declare souvent une carte perdue depuis
« Mon compte » pour tester. La carte redevient libre, et il faut la relier a la
main. Cette commande refait exactement ce que fait le bouton « lier ma carte »
(BaseBillet/views.py, ScanQrCode.link), sans passer par le navigateur.
/ Why: in dev we often declare a card lost to test, then need to link it back.
This command does exactly what the "link my card" flow does, without a browser.

FLUX (le meme que la vue, dans cet ordre) :
1. Recupere le portefeuille de l'utilisateur chez Fedow (get_or_create_wallet).
2. Verifie que cet utilisateur n'a pas deja une carte chez Fedow (anti-vol de
   carte : sans ce controle, connaitre un email suffirait a capter un wallet).
3. Fedow fusionne le portefeuille temporaire de la carte dans celui du user
   (linkwallet_cardqrcode).
4. Lespass rattache la carte au user (CarteService.lier_a_user). Sans cette
   etape, CarteCashless.user reste vide : la caisse V2 voit une carte anonyme,
   masque le solde federe et ne reconnait pas l'adherent au comptoir.
/ FLOW: wallet, anti-theft check, Fedow merge, then the local Lespass link.

MULTI-TENANT : les cartes (CarteCashless) vivent dans le schema public, mais
l'utilisateur et la configuration Fedow appartiennent a un tenant. On se place
donc toujours dans un tenant avec tenant_context.
/ MULTI-TENANT: cards live in the public schema, but the user and the Fedow
config belong to a tenant, so we always run inside tenant_context.

Exemples / Usage :
    # Voir les cartes et leur proprietaire (n'ecrit rien) :
    docker exec lespass_django poetry run python manage.py lier_carte --lister

    # Lier une carte a un compte :
    docker exec lespass_django poetry run python manage.py lier_carte --email admin@admin.com --carte 33BC1DC3

    # Sur un autre tenant que lespass :
    docker exec lespass_django poetry run python manage.py lier_carte --email admin@admin.com --carte 33BC1DC3 --schema festival

Pour DELIER une carte : passer par « Mon compte » > carte perdue, cote navigateur.
/ To UNLINK a card: use "my account" > lost card in the browser.
"""

import argparse
import logging

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import tenant_context

from Customers.models import Client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Lie une carte cashless au compte d'un utilisateur, chez Fedow et dans Lespass. "
        "Utiliser --lister pour voir les cartes disponibles."
    )

    def add_arguments(self, parser):
        parser.formatter_class = argparse.RawTextHelpFormatter
        parser.add_argument(
            "--email",
            type=str,
            default=None,
            help="Email du compte qui recoit la carte. Ex : admin@admin.com",
        )
        parser.add_argument(
            "--carte",
            type=str,
            default=None,
            help="Numero imprime sur la carte (8 caracteres). Ex : 33BC1DC3",
        )
        parser.add_argument(
            "--schema",
            type=str,
            default="lespass",
            help="Tenant (schema_name) ou se trouve l'utilisateur. Defaut : lespass",
        )
        parser.add_argument(
            "--lister",
            action="store_true",
            help="Affiche toutes les cartes avec leur proprietaire, puis s'arrete.",
        )

    def handle(self, *args, **options):
        # Les imports sont faits ici, pas en haut du fichier : Django doit avoir
        # fini de charger les applications avant qu'on touche aux modeles.
        # / Imports live here so Django finishes loading apps first.
        from AuthBillet.models import TibilletUser
        from QrcodeCashless.models import CarteCashless
        from fedow_connect.fedow_api import FedowAPI
        from fedow_core.exceptions import CarteDejaLiee, CarteIntrouvable, UserADejaCarte
        from fedow_core.services import CarteService

        nom_du_schema = options["schema"]
        try:
            tenant = Client.objects.get(schema_name=nom_du_schema)
        except Client.DoesNotExist:
            raise CommandError(f"Tenant introuvable : {nom_du_schema}")

        # --lister : on affiche l'etat des cartes et on s'arrete. Aucune ecriture.
        # / --lister: show the cards and stop. Nothing is written.
        if options["lister"]:
            self.lister_les_cartes(CarteCashless)
            return

        email_du_compte = options["email"]
        numero_de_la_carte = options["carte"]
        if not email_du_compte or not numero_de_la_carte:
            raise CommandError(
                "Il faut --email ET --carte. Exemple : "
                "--email admin@admin.com --carte 33BC1DC3 "
                "(ou --lister pour voir les cartes)"
            )
        numero_de_la_carte = numero_de_la_carte.strip().upper()

        with tenant_context(tenant):
            try:
                utilisateur = TibilletUser.objects.get(email=email_du_compte)
            except TibilletUser.DoesNotExist:
                raise CommandError(
                    f"Utilisateur introuvable dans le tenant {nom_du_schema} : {email_du_compte}"
                )

            try:
                carte = CarteCashless.objects.get(number=numero_de_la_carte)
            except CarteCashless.DoesNotExist:
                raise CommandError(
                    f"Carte introuvable : {numero_de_la_carte}. "
                    "Lancer --lister pour voir les numeros existants."
                )

            # La carte doit avoir un uuid : c'est lui qui identifie la carte chez
            # Fedow. Une carte sans uuid n'est pas identifiable, on s'arrete.
            # / The card needs its uuid: it identifies the card on Fedow.
            if not carte.uuid:
                raise CommandError(
                    f"La carte {numero_de_la_carte} n'a pas d'uuid : elle n'est pas identifiable."
                )

            # Carte deja liee : on ne touche a rien. Si c'est deja le bon compte,
            # c'est un succes ; sinon on refuse plutot que de voler la carte.
            # / Already linked: do nothing. Same user = success, other user = refuse.
            if carte.user:
                if carte.user.email == email_du_compte:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Rien a faire : la carte {numero_de_la_carte} est deja liee a {email_du_compte}."
                        )
                    )
                    return
                raise CommandError(
                    f"La carte {numero_de_la_carte} appartient deja a {carte.user.email}. "
                    "La delier d'abord (« Mon compte » > carte perdue)."
                )

            fedow_api = FedowAPI()

            # Etape 1 : le portefeuille de l'utilisateur chez Fedow.
            # / Step 1: the user's wallet on Fedow.
            portefeuille, portefeuille_vient_d_etre_cree = fedow_api.wallet.get_or_create_wallet(utilisateur)
            self.stdout.write(
                f"1. Portefeuille Fedow : {portefeuille} (cree : {portefeuille_vient_d_etre_cree})"
            )

            # Etape 2 : anti-vol de carte. Un portefeuille ne porte qu'une carte.
            # / Step 2: anti card theft. One wallet holds a single card.
            if not portefeuille_vient_d_etre_cree:
                portefeuille_serialise = fedow_api.wallet.retrieve_by_signature(utilisateur).validated_data
                if portefeuille_serialise["has_user_card"]:
                    raise CommandError(
                        f"{email_du_compte} a deja une carte chez Fedow. "
                        "La declarer perdue d'abord (« Mon compte » > carte perdue)."
                    )
            self.stdout.write("2. Aucune carte deja liee a ce compte chez Fedow.")

            # Etape 3 : Fedow fusionne le portefeuille temporaire de la carte.
            # / Step 3: Fedow merges the card's temporary wallet.
            carte_liee_chez_fedow = fedow_api.NFCcard.linkwallet_cardqrcode(
                user=utilisateur,
                qrcode_uuid=carte.uuid,
            )
            if not carte_liee_chez_fedow:
                raise CommandError(
                    f"Fedow a refuse la liaison de la carte {numero_de_la_carte}. "
                    "Carte inconnue de Fedow ou pas encore activee."
                )
            self.stdout.write("3. Fedow a fusionne le portefeuille de la carte.")

            # Etape 4 : liaison locale. Sans elle, la caisse V2 voit une carte anonyme.
            # / Step 4: local link. Without it the V2 POS sees an anonymous card.
            try:
                CarteService.lier_a_user(
                    qrcode_uuid=carte.uuid,
                    user=utilisateur,
                    ip="127.0.0.1",
                )
            except CarteIntrouvable:
                raise CommandError(
                    f"Incoherence : Fedow a lie la carte {numero_de_la_carte}, "
                    "mais elle est absente de la base Lespass."
                )
            except (CarteDejaLiee, UserADejaCarte) as erreur_de_liaison_locale:
                raise CommandError(
                    f"Incoherence : Fedow a lie la carte {numero_de_la_carte}, "
                    f"mais la base Lespass refuse : {erreur_de_liaison_locale}"
                )
            self.stdout.write("4. Carte rattachee au compte dans Lespass.")

            self.stdout.write(
                self.style.SUCCESS(
                    f"OK : carte {numero_de_la_carte} liee a {email_du_compte} (tenant {nom_du_schema})."
                )
            )

    def lister_les_cartes(self, CarteCashless):
        """
        Affiche chaque carte avec son proprietaire, ou LIBRE si elle n'est liee a personne.
        / Prints each card with its owner, or LIBRE when it belongs to nobody.

        :param CarteCashless: le modele carte (passe en argument pour eviter un import en haut du fichier)
        """
        toutes_les_cartes = CarteCashless.objects.select_related("user").order_by("number")
        if not toutes_les_cartes:
            self.stdout.write(self.style.WARNING("Aucune carte en base."))
            return

        for carte in toutes_les_cartes:
            if carte.user:
                self.stdout.write(f"{carte.number}  {carte.user.email}")
            else:
                self.stdout.write(f"{carte.number}  {self.style.SUCCESS('LIBRE')}")
