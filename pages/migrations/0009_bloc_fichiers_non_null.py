# Champs fichier (image, image_secondaire, video, auteur_photo) passes en NOT NULL.
# Idiomatique Django : un FileField vide vaut "" et jamais NULL. Cela evite aussi un
# crash de django-stdimage (delete_orphans appelle .delete() sur un champ NULL).
# / File fields switched to NOT NULL. Idiomatic Django: an empty FileField is ""
# never NULL. Also avoids a django-stdimage crash (delete_orphans calls .delete()
# on a NULL field).

import stdimage.models
from django.db import migrations, models


def vider_nulls(apps, schema_editor):
    # Met "" la ou la valeur est NULL (update bulk : aucun signal stdimage).
    # / Set "" where the value is NULL (bulk update: no stdimage signal fired).
    Bloc = apps.get_model("pages", "Bloc")
    for champ in ("image", "image_secondaire", "video", "auteur_photo"):
        Bloc.objects.filter(**{f"{champ}__isnull": True}).update(**{champ: ""})


class Migration(migrations.Migration):

    # atomic=False : l'UPDATE de donnees doit etre COMMITE avant l'ALTER ... SET NOT
    # NULL, sinon PostgreSQL refuse (« cannot ALTER TABLE because it has pending
    # trigger events »). Chaque operation gere donc sa propre transaction.
    # / atomic=False: the data UPDATE must be COMMITTED before the ALTER ... SET NOT
    # NULL, otherwise PostgreSQL refuses (pending trigger events).
    atomic = False

    dependencies = [
        ("pages", "0008_remove_bloc_image_secondaire_statique_and_more"),
    ]

    operations = [
        migrations.RunPython(vider_nulls, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="bloc",
            name="image",
            field=stdimage.models.StdImageField(
                blank=True,
                force_min_size=False,
                help_text="Image du bloc (fond du Hero ou illustration laterale).",
                upload_to="images/pages/",
                variations={
                    "fhd": (1920, 1920),
                    "hdr": (1280, 1280),
                    "med": (480, 480),
                    "thumbnail": (150, 90),
                    "crop_hdr": (960, 540, True),
                    "crop": (480, 270, True),
                    "social_card": (1200, 630, True),
                },
                verbose_name="Image",
            ),
        ),
        migrations.AlterField(
            model_name="bloc",
            name="image_secondaire",
            field=stdimage.models.StdImageField(
                blank=True,
                force_min_size=False,
                help_text="Image secondaire (ex. badge date, logo a cote d'une carte).",
                upload_to="images/pages/",
                variations={
                    "fhd": (1920, 1920),
                    "hdr": (1280, 1280),
                    "med": (480, 480),
                    "thumbnail": (150, 90),
                    "crop_hdr": (960, 540, True),
                    "crop": (480, 270, True),
                    "social_card": (1200, 630, True),
                },
                verbose_name="Seconde image",
            ),
        ),
        migrations.AlterField(
            model_name="bloc",
            name="video",
            field=models.FileField(
                blank=True,
                help_text="Fichier video (mp4/webm) pour le bloc Video + texte.",
                upload_to="videos/pages/",
                verbose_name="Video",
            ),
        ),
        migrations.AlterField(
            model_name="bloc",
            name="auteur_photo",
            field=stdimage.models.StdImageField(
                blank=True,
                force_min_size=False,
                help_text="Portrait de la personne qui temoigne (optionnel).",
                upload_to="images/pages/auteurs/",
                variations={"med": (480, 480), "thumbnail": (150, 150, True)},
                verbose_name="Photo de l'auteur",
            ),
        ),
    ]
