"""
Galerie d'images d'un évènement dans l'admin : miniatures + envoi de plusieurs images.
/ Event image gallery in the admin: thumbnails + multiple image upload.

LOCALISATION : tests/pytest/test_admin_galerie_evenement.py

Code testé :
- Administration/admin_tenant.py : EventForm (champs « carrousel » et
  « galerie_nouvelles_images »), PlusieursImagesField, EventAdmin.save_related
- Administration/templates/admin/event/widget_galerie_carrousel.html
- BaseBillet/models.py : Carrousel (nom facultatif, pas de taille minimale)

Ces tests tournent sur la base de DEV : chaque test supprime ce qu'il crée.
/ These tests run on the DEV database: each test deletes what it creates.
"""

import datetime
import io
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.utils import timezone
from django.utils.datastructures import MultiValueDict
from django_tenants.utils import tenant_context
from PIL import Image


def _fichier_image(nom_du_fichier, largeur=200, hauteur=100):
    """
    Fabrique une petite image PNG en mémoire, prête à être envoyée par un formulaire.
    / Builds a small in-memory PNG, ready to be sent through a form.
    """
    tampon = io.BytesIO()
    Image.new("RGB", (largeur, hauteur), color=(200, 30, 30)).save(tampon, format="PNG")
    return SimpleUploadedFile(
        nom_du_fichier, tampon.getvalue(), content_type="image/png"
    )


def _creer_evenement(nom):
    """
    Crée un évènement futur. `img=""` et `sticker_img=""` sont indispensables :
    laissés à NULL, la suppression de l'évènement plante (tests/PIEGES.md,
    delete_orphans de django-stdimage).
    / Creates a future event. img="" and sticker_img="" are required to delete it later.
    """
    from BaseBillet.models import Event

    return Event.objects.create(
        name=nom,
        datetime=timezone.now() + datetime.timedelta(days=30),
        img="",
        sticker_img="",
    )


def _donnees_du_formulaire(evenement, images_cochees):
    """
    Données POST minimales pour modifier l'évènement depuis la fiche admin.
    / Minimal POST data to edit the event from the admin page.
    """
    # La date passe par le widget de l'admin en deux morceaux (jour, heure).
    # / The admin widget splits the date in two parts (day, time).
    debut_local = timezone.localtime(evenement.datetime)
    return {
        "name": evenement.name,
        "datetime_0": debut_local.strftime("%Y-%m-%d"),
        "datetime_1": debut_local.strftime("%H:%M:%S"),
        "jauge_max": 50,
        "refund_deadline": 7,
        "carrousel": [str(image.pk) for image in images_cochees],
    }


def _formulaire_de_l_admin(evenement, donnees, fichiers=None):
    """
    Construit le formulaire comme l'admin : get_form() limite EventForm aux champs
    des fieldsets. EventForm seul (fields='__all__') exigerait des champs que la
    fiche n'affiche pas.
    / Builds the form like the admin: get_form() limits EventForm to the fieldsets.
    """
    from Administration.admin_tenant import EventAdmin, staff_admin_site
    from BaseBillet.models import Event

    admin_des_evenements = EventAdmin(Event, staff_admin_site)
    requete = RequestFactory().post("/admin/BaseBillet/event/")
    # get_form() vérifie la permission de modifier : un superuser suffit.
    # / get_form() checks the change permission: a superuser is enough.
    requete.user = SimpleNamespace(
        is_superuser=True, is_authenticated=True, is_active=True
    )
    classe_du_formulaire = admin_des_evenements.get_form(
        requete, evenement, change=True
    )
    return classe_du_formulaire(data=donnees, files=fichiers, instance=evenement)


def _enregistrer_comme_l_admin(formulaire):
    """
    Enregistre le formulaire comme le fait l'admin : save_model puis save_related.
    / Saves the form the way the admin does: save_model then save_related.
    """
    from Administration.admin_tenant import EventAdmin, staff_admin_site
    from BaseBillet.models import Event

    admin_des_evenements = EventAdmin(Event, staff_admin_site)
    requete = RequestFactory().post("/admin/BaseBillet/event/")
    evenement_modifie = formulaire.save(commit=False)
    evenement_modifie.save()
    admin_des_evenements.save_related(requete, formulaire, [], True)
    return evenement_modifie


@pytest.mark.django_db
def test_la_galerie_ne_liste_que_les_images_de_l_evenement(tenant):
    """
    Le champ galerie ne propose que les images liées à l'évènement, en miniatures.
    Une diapositive d'un autre évènement n'apparaît pas.
    / The gallery field only lists the event's own images, as thumbnails.
    """
    from Administration.admin_tenant import EventForm
    from BaseBillet.models import Carrousel

    with tenant_context(tenant):
        evenement = _creer_evenement("Galerie admin — liste")
        image_de_l_evenement = Carrousel.objects.create(img=_fichier_image("liee.png"))
        image_d_ailleurs = Carrousel.objects.create(img=_fichier_image("ailleurs.png"))
        try:
            evenement.carrousel.add(image_de_l_evenement)

            formulaire = EventForm(instance=evenement)
            images_proposees = list(formulaire.fields["carrousel"].queryset)
            assert images_proposees == [image_de_l_evenement]

            html_du_champ = str(formulaire["carrousel"])
            assert 'data-testid="admin-event-galerie-image"' in html_du_champ
            assert image_de_l_evenement.img.med.url in html_du_champ
            assert image_d_ailleurs.img.med.url not in html_du_champ
        finally:
            evenement.delete()
            image_de_l_evenement.delete()
            image_d_ailleurs.delete()


@pytest.mark.django_db
def test_envoyer_deux_images_cree_deux_diapositives_liees_a_l_evenement(tenant):
    """
    Deux fichiers dans « Ajouter des images » : deux diapositives sans nom,
    rattachées à l'évènement, en plus de l'image déjà cochée.
    / Two uploaded files: two unnamed slides linked to the event, plus the checked one.
    """
    from BaseBillet.models import Carrousel

    with tenant_context(tenant):
        evenement = _creer_evenement("Galerie admin — envoi")
        image_deja_la = Carrousel.objects.create(img=_fichier_image("deja_la.png"))
        diapositives_a_supprimer = [image_deja_la]
        try:
            evenement.carrousel.add(image_deja_la)

            fichiers_envoyes = MultiValueDict(
                {
                    "galerie_nouvelles_images": [
                        _fichier_image("nouvelle_1.png"),
                        _fichier_image("nouvelle_2.png"),
                    ],
                }
            )
            formulaire = _formulaire_de_l_admin(
                evenement,
                _donnees_du_formulaire(evenement, [image_deja_la]),
                fichiers_envoyes,
            )
            assert formulaire.is_valid(), formulaire.errors

            evenement_modifie = _enregistrer_comme_l_admin(formulaire)
            images_de_l_evenement = list(evenement_modifie.carrousel.all())
            diapositives_a_supprimer = images_de_l_evenement

            assert len(images_de_l_evenement) == 3
            assert image_deja_la in images_de_l_evenement
            for diapositive in images_de_l_evenement:
                if diapositive.pk != image_deja_la.pk:
                    assert diapositive.name == ""
                    assert diapositive.on_event_list_page is False
        finally:
            evenement.delete()
            for diapositive in diapositives_a_supprimer:
                diapositive.delete()


@pytest.mark.django_db
def test_decocher_une_image_la_retire_de_l_evenement_sans_la_supprimer(tenant):
    """
    Décocher une image : elle n'est plus liée à l'évènement, mais la diapositive
    existe toujours (admin Carrousel).
    / Unchecking unlinks the image from the event; the slide still exists.
    """
    from BaseBillet.models import Carrousel

    with tenant_context(tenant):
        evenement = _creer_evenement("Galerie admin — retrait")
        image_a_retirer = Carrousel.objects.create(img=_fichier_image("a_retirer.png"))
        try:
            evenement.carrousel.add(image_a_retirer)

            formulaire = _formulaire_de_l_admin(
                evenement,
                _donnees_du_formulaire(evenement, []),
            )
            assert formulaire.is_valid(), formulaire.errors
            evenement_modifie = _enregistrer_comme_l_admin(formulaire)

            assert evenement_modifie.carrousel.count() == 0
            assert Carrousel.objects.filter(pk=image_a_retirer.pk).exists()
        finally:
            evenement.delete()
            image_a_retirer.delete()


@pytest.mark.django_db
def test_un_fichier_qui_n_est_pas_une_image_est_refuse(tenant):
    """
    Un fichier texte dans « Ajouter des images » : erreur sur ce champ.
    / A text file in "Add images" gives an error on that field.
    """
    from Administration.admin_tenant import EventForm

    with tenant_context(tenant):
        evenement = _creer_evenement("Galerie admin — refus")
        try:
            faux_fichier = SimpleUploadedFile(
                "notes.txt", b"pas une image", content_type="text/plain"
            )
            formulaire = EventForm(
                data=_donnees_du_formulaire(evenement, []),
                files=MultiValueDict({"galerie_nouvelles_images": [faux_fichier]}),
                instance=evenement,
            )
            assert not formulaire.is_valid()
            assert "galerie_nouvelles_images" in formulaire.errors
        finally:
            evenement.delete()


@pytest.mark.django_db
def test_une_petite_image_est_acceptee_comme_diapositive(tenant):
    """
    Pas de taille minimale : une image de 100 x 50 passe la validation du modèle.
    / No minimum size: a 100 x 50 image passes model validation.
    """
    from BaseBillet.models import Carrousel

    with tenant_context(tenant):
        petite_diapositive = Carrousel(
            img=_fichier_image("petite.png", largeur=100, hauteur=50)
        )
        petite_diapositive.full_clean()


@pytest.mark.django_db
def test_un_evenement_neuf_a_une_galerie_vide(tenant):
    """
    Un évènement pas encore enregistré a déjà un pk (UUID) : la galerie doit quand même
    être vide, sans requête sur ses images.
    / A not-yet-saved event already has a UUID pk: the gallery must still be empty.
    """
    from Administration.admin_tenant import EventForm
    from BaseBillet.models import Event

    with tenant_context(tenant):
        formulaire = EventForm(instance=Event())
        assert list(formulaire.fields["carrousel"].queryset) == []


@pytest.mark.django_db
def test_plus_de_20_images_d_un_coup_sont_refusees(tenant):
    """Au-delà du plafond, erreur explicite sur le champ. / Over the cap: explicit error."""
    with tenant_context(tenant):
        evenement = _creer_evenement("Galerie admin — plafond")
        try:
            fichiers_envoyes = MultiValueDict(
                {
                    "galerie_nouvelles_images": [
                        _fichier_image(f"image_{numero}.png") for numero in range(21)
                    ],
                }
            )
            formulaire = _formulaire_de_l_admin(
                evenement, _donnees_du_formulaire(evenement, []), fichiers_envoyes
            )
            assert not formulaire.is_valid()
            assert (
                "Au plus 20 images par envoi."
                in formulaire.errors["galerie_nouvelles_images"]
            )
        finally:
            evenement.delete()


@pytest.mark.django_db
def test_l_erreur_d_un_fichier_invalide_donne_son_nom(tenant):
    """Sur plusieurs fichiers, l'erreur dit lequel est fautif. / The error names the file."""
    with tenant_context(tenant):
        evenement = _creer_evenement("Galerie admin — nom du fichier")
        try:
            fichiers_envoyes = MultiValueDict(
                {
                    "galerie_nouvelles_images": [
                        _fichier_image("bonne.png"),
                        SimpleUploadedFile(
                            "affiche_cassee.png",
                            b"pas une image",
                            content_type="image/png",
                        ),
                    ],
                }
            )
            formulaire = _formulaire_de_l_admin(
                evenement, _donnees_du_formulaire(evenement, []), fichiers_envoyes
            )
            assert not formulaire.is_valid()
            assert "affiche_cassee.png" in str(
                formulaire.errors["galerie_nouvelles_images"]
            )
        finally:
            evenement.delete()
