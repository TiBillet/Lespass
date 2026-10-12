"""
Refabrique les miniatures des photos qui portent une orientation EXIF.
/ Rebuilds the thumbnails of photos carrying an EXIF orientation.

LOCALISATION : pages/management/commands/regenerer_variations_exif.py

POURQUOI :
Les miniatures stdimage fabriquees AVANT BaseBillet/images_orientation.py sont
couchees pour toute photo de telephone (orientation EXIF 3, 6, 8...). Le fichier
original, lui, est intact : il suffit de refabriquer ses miniatures, ce que fait
cette commande. Les photos deja droites (orientation 1 ou absente) ne sont pas
touchees.
/ Thumbnails built before the fix are rotated for phone photos. The original is
intact: rebuilding its thumbnails is enough. Upright photos are left alone.

Usage :
    # Passage a blanc (par defaut) : compte les photos a redresser, n'ecrit rien.
    # / Dry run (default): counts photos to straighten, writes nothing.
    python manage.py regenerer_variations_exif --tenant universite-populaire-villeurbanne

    # Ecriture reelle, un lieu.
    # / Real write, one venue.
    python manage.py regenerer_variations_exif --tenant universite-populaire-villeurbanne --appliquer

    # Tous les lieux, l'un apres l'autre.
    # / Every venue, one after the other.
    python manage.py regenerer_variations_exif --tous --appliquer

PERIMETRE :
Les modeles des TENANT_APPS (BaseBillet, pages, crowds...), lieu par lieu.
Les modeles des seules SHARED_APPS (MetaBillet, QrcodeCashless) vivent dans le
schema public et ne portent pas de photos de lieu : ils ne sont pas parcourus.
/ TENANT_APPS models, venue by venue. Shared-only apps are not scanned.

CE QUE LA COMMANDE ECRIT :
Seulement les fichiers de miniatures (stockage media). Aucune ligne de base de
donnees n'est modifiee : le nom du fichier original ne change pas.
/ Only thumbnail files are written. No database row changes.

REJOUABLE :
L'original garde son etiquette EXIF (seules les miniatures sont redressees). Un
second passage recompte donc les memes photos et les refabrique a l'identique :
c'est sans effet, juste du temps de calcul.
/ The original keeps its EXIF tag, so a second run counts the same photos again
and rebuilds identical thumbnails: harmless, only CPU time.
"""

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import tenant_context
from PIL import Image, UnidentifiedImageError
from stdimage.models import StdImageField

from BaseBillet.images_orientation import ORIENTATION_DEJA_DROITE, lire_orientation_exif
from Customers.models import Client


def champs_image_des_modeles_de_lieu():
    """
    Liste les couples (modele, nom du champ StdImageField) des TENANT_APPS.
    / Lists (model, StdImageField name) pairs of the TENANT_APPS.
    """
    noms_des_applications_de_lieu = set(settings.TENANT_APPS)
    couples_modele_champ = []
    for modele in apps.get_models():
        nom_application = modele._meta.app_config.name
        if nom_application not in noms_des_applications_de_lieu:
            continue
        # Un modele proxy partage la table de son modele : on la lirait deux fois.
        # / A proxy model shares its parent's table: it would be read twice.
        if modele._meta.proxy:
            continue
        for champ in modele._meta.get_fields():
            if isinstance(champ, StdImageField):
                couples_modele_champ.append((modele, champ.name))
    return couples_modele_champ


class Command(BaseCommand):
    help = (
        "Refabrique les miniatures des photos portant une orientation EXIF "
        "(passage a blanc par defaut, --appliquer pour ecrire)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="schema_name du lieu a traiter")
        parser.add_argument(
            "--tous",
            action="store_true",
            help="traiter tous les lieux, l'un apres l'autre",
        )
        parser.add_argument(
            "--appliquer", action="store_true", help="ecrire reellement les miniatures"
        )

    def handle(self, *args, **options):
        schema_demande = options["tenant"]
        tous_les_lieux = options["tous"]
        ecriture_reelle = options["appliquer"]

        if bool(schema_demande) == bool(tous_les_lieux):
            raise CommandError("Indiquer soit --tenant <schema>, soit --tous.")

        if tous_les_lieux:
            lieux_a_traiter = Client.objects.exclude(schema_name="public").order_by(
                "schema_name"
            )
        else:
            lieux_a_traiter = Client.objects.filter(schema_name=schema_demande)
            if not lieux_a_traiter.exists():
                raise CommandError(f"Lieu introuvable : {schema_demande}")

        if not ecriture_reelle:
            self.stdout.write(
                "PASSAGE A BLANC : rien n'est ecrit. Ajouter --appliquer pour ecrire."
            )

        couples_modele_champ = champs_image_des_modeles_de_lieu()

        for lieu in lieux_a_traiter:
            with tenant_context(lieu):
                self.traiter_un_lieu(lieu, couples_modele_champ, ecriture_reelle)

    def traiter_un_lieu(self, lieu, couples_modele_champ, ecriture_reelle):
        """
        Parcourt les images d'un lieu, et refabrique les miniatures des photos
        dont l'orientation EXIF n'est pas « deja droite ».
        / Walks a venue's images and rebuilds thumbnails of non-upright photos.
        """
        nombre_images_lues = 0
        nombre_images_a_redresser = 0
        nombre_images_illisibles = 0

        for modele, nom_du_champ in couples_modele_champ:
            objets_avec_image = modele.objects.exclude(**{nom_du_champ: ""}).exclude(
                **{f"{nom_du_champ}__isnull": True}
            )
            for objet in objets_avec_image.iterator():
                fichier_image = getattr(objet, nom_du_champ)
                nombre_images_lues += 1

                # Lecture de l'orientation sur le fichier ORIGINAL.
                # Fichier absent du stockage ou pas une image : on compte et on passe.
                # / Read orientation from the ORIGINAL file. Missing or not an image: count and skip.
                try:
                    with fichier_image.storage.open(
                        fichier_image.name
                    ) as fichier_ouvert:
                        with Image.open(fichier_ouvert) as image:
                            orientation = lire_orientation_exif(image)
                except (FileNotFoundError, OSError, UnidentifiedImageError):
                    nombre_images_illisibles += 1
                    continue

                if orientation == ORIENTATION_DEJA_DROITE:
                    continue

                nombre_images_a_redresser += 1
                self.stdout.write(
                    f"  [{lieu.schema_name}] {modele.__name__}.{nom_du_champ} "
                    f"pk={objet.pk} orientation={orientation} {fichier_image.name}"
                )
                if ecriture_reelle:
                    fichier_image.render_variations(replace=True)

        verbe = "redressees" if ecriture_reelle else "a redresser"
        self.stdout.write(
            f"[{lieu.schema_name}] {nombre_images_lues} images lues, "
            f"{nombre_images_a_redresser} {verbe}, {nombre_images_illisibles} illisibles."
        )
