"""
Cree une ou plusieurs cartes NFC de test (CarteCashless) rattachees au tenant "lespass".
/ Creates one or more test NFC cards (CarteCashless) linked to the "lespass" tenant.

LOCALISATION : QrcodeCashless/management/commands/create_test_carte.py

CarteCashless et Detail sont dans SHARED_APPS (schema public).
Le Detail est cree avec origine = Client "lespass" (le tenant de dev).

LANCEMENT :
    # Creer une carte avec le tag_id lu par le lecteur RFID
    docker exec lespass_django poetry run python manage.py create_test_carte 741ECC2A

    # Creer plusieurs cartes d'un coup
    docker exec lespass_django poetry run python manage.py create_test_carte 741ECC2A AABB1122 DEADBEEF
"""

import uuid
import random
import string

from django.core.management.base import BaseCommand

from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail

# Nom du schema tenant utilise comme origine des cartes de test.
# / Schema name of the tenant used as origin for test cards.
SCHEMA_TENANT_ORIGINE = "lespass"


def generer_number_aleatoire():
    """
    Genere un numero de carte aleatoire de 8 caracteres (chiffres + lettres majuscules).
    Verifie que le numero n'existe pas deja en base.
    / Generates a random 8-char card number. Checks uniqueness in DB.
    """
    caracteres_autorises = string.ascii_uppercase + string.digits
    for tentative in range(100):
        number_genere = "".join(random.choices(caracteres_autorises, k=8))

        # On verifie que ce numero n'existe pas deja en base.
        # / Check this number doesn't already exist in DB.
        number_existe_deja = CarteCashless.objects.filter(number=number_genere).exists()
        if not number_existe_deja:
            return number_genere

    # Si on arrive ici, c'est qu'on a eu 100 collisions. Tres improbable.
    # / 100 collisions in a row. Extremely unlikely.
    raise RuntimeError("Impossible de generer un numero unique apres 100 tentatives")


def obtenir_ou_creer_detail_test(tenant_lespass):
    """
    Recupere ou cree un Detail de test rattache au tenant lespass.
    On reutilise le meme Detail pour toutes les cartes de test
    (base_url = "TEST", generation = 0).
    / Gets or creates a test Detail linked to the lespass tenant.

    :param tenant_lespass: Client — le tenant "lespass"
    :return: Detail
    """
    detail_test, _detail_cree = Detail.objects.get_or_create(
        base_url="TEST",
        origine=tenant_lespass,
        defaults={
            "generation": 0,
        },
    )
    return detail_test


class Command(BaseCommand):
    help = (
        "Cree des cartes NFC de test (CarteCashless) avec un tag_id en argument, "
        "rattachees au tenant lespass comme origine."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "tag_ids",
            nargs="+",
            type=str,
            help="Un ou plusieurs tag_id hexadecimaux (ex: 741ECC2A AABB1122)",
        )

    def handle(self, *args, **options):
        """
        Pour chaque tag_id en argument :
        1. Normalise en majuscules
        2. Verifie le format (hex, max 8 chars)
        3. Cree la carte avec un Detail origine=lespass si elle n'existe pas deja
        / For each tag_id: normalize, validate, create with origin=lespass if not exists.
        """

        # Recuperation du tenant "lespass" comme origine des cartes.
        # / Get the "lespass" tenant as card origin.
        tenant_lespass = Client.objects.filter(schema_name=SCHEMA_TENANT_ORIGINE).first()
        if tenant_lespass is None:
            self.stderr.write(
                f"ERREUR : tenant '{SCHEMA_TENANT_ORIGINE}' introuvable en base. "
                f"Verifiez que le tenant de dev existe."
            )
            return

        # On reutilise un seul Detail pour toutes les cartes de test.
        # / Reuse a single Detail for all test cards.
        detail_test = obtenir_ou_creer_detail_test(tenant_lespass)

        self.stdout.write(
            f"Origine : tenant '{tenant_lespass.schema_name}' "
            f"(Detail base_url='{detail_test.base_url}')"
        )

        liste_tag_ids = options["tag_ids"]
        nombre_cartes_creees = 0

        for tag_id_argument in liste_tag_ids:

            # Normalisation du tag_id : majuscules, sans espaces.
            # Le lecteur RFID renvoie des hex en majuscules (ex: "741ECC2A").
            # / Normalize tag_id: uppercase, stripped.
            tag_id_normalise = tag_id_argument.strip().upper()

            # Verification : le tag_id doit faire 8 caracteres hexadecimaux max.
            # / Validation: tag_id must be at most 8 hex characters.
            tag_id_est_trop_long = len(tag_id_normalise) > 8
            if tag_id_est_trop_long:
                self.stderr.write(
                    f"ERREUR : tag_id '{tag_id_normalise}' fait "
                    f"{len(tag_id_normalise)} caracteres (max 8)."
                )
                continue

            tag_id_est_hex_valide = all(c in "0123456789ABCDEF" for c in tag_id_normalise)
            if not tag_id_est_hex_valide:
                self.stderr.write(
                    f"ERREUR : tag_id '{tag_id_normalise}' contient "
                    f"des caracteres non hexadecimaux."
                )
                continue

            # Verification : une carte avec ce tag_id existe peut-etre deja.
            # / Check: a card with this tag_id may already exist.
            carte_existante = CarteCashless.objects.filter(tag_id=tag_id_normalise).first()
            if carte_existante is not None:
                self.stdout.write(
                    f"EXISTE DEJA : tag_id={carte_existante.tag_id}, "
                    f"number={carte_existante.number}, uuid={carte_existante.uuid}"
                )
                continue

            # Generation des champs aleatoires.
            # / Generate random fields.
            uuid_genere = uuid.uuid4()
            number_genere = generer_number_aleatoire()

            # Creation de la carte en base avec le Detail de test.
            # / Create card in database with test Detail.
            carte_creee = CarteCashless.objects.create(
                tag_id=tag_id_normalise,
                uuid=uuid_genere,
                number=number_genere,
                detail=detail_test,
            )

            self.stdout.write(
                f"CREE : tag_id={carte_creee.tag_id}, "
                f"number={carte_creee.number}, uuid={carte_creee.uuid}"
            )
            nombre_cartes_creees += 1

        self.stdout.write(f"\nTermine. {nombre_cartes_creees} carte(s) creee(s).")
