"""
Tests de l'écran kiosk (couleur d'accent, états vides) et de la calibration.
/ Tests for the kiosk screen (accent color, empty states) and calibration.

LOCALISATION : tests/pytest/test_controlvanne_ecran_calibration.py

Couvre les corrections des lots 3 et 4 de l'audit du 2026-09-26 :
- rendu du kiosk : couleur d'accent du fût, écran « Aucun fût branché » ;
- palette des couleurs de fût : exactement la palette « Létireuz » ;
- calibration : serializer, erreurs en 422, application du facteur,
  « Nouvelle série » datée par le serveur ;
- FutProductForm : couleur hors format refusée.
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string
from django_tenants.utils import schema_context, tenant_context


# ─────────────────────────────────────────────────────────────────────
# Rendu du kiosk / Kiosk rendering
# ─────────────────────────────────────────────────────────────────────


# Palette « Létireuz » : design tokens --color-tireuse-{teinte}, dans l'ordre.
# / "Létireuz" palette: --color-tireuse-{hue} design tokens, in order.
PALETTE_LETIREUZ = [
    "#0f96f0",  # blue
    "#009eb3",  # teal
    "#884dff",  # violet
    "#00a84c",  # green
    "#ff589f",  # pink
    "#a89500",  # olive
    "#9d6401",  # brown
    "#fa6000",  # orange
    "#fd2629",  # red
    "#2ca300",  # lime
    "#5757ff",  # indigo
]


class TestPaletteDesFuts:
    """
    L'admin propose exactement la palette « Létireuz », sans variante inventée.
    / The admin offers exactly the "Létireuz" palette, no invented variant.
    """

    def test_01_les_couleurs_proposees_sont_la_palette_letireuz(self):
        """Les 11 couleurs, dans l'ordre du nuancier. / The 11 colors, in order."""
        from Administration.admin.products import COULEURS_ACCENT

        codes_des_couleurs_proposees = []
        for code_couleur, _nom_couleur in COULEURS_ACCENT:
            codes_des_couleurs_proposees.append(code_couleur)

        assert codes_des_couleurs_proposees == PALETTE_LETIREUZ

    def test_02_chaque_code_est_en_minuscules(self):
        """Le widget compare la couleur du fût en minuscules : la liste doit l'être aussi."""
        from Administration.admin.products import COULEURS_ACCENT

        for code_couleur, nom_couleur in COULEURS_ACCENT:
            assert code_couleur == code_couleur.lower(), nom_couleur


class _TagsFictifs:
    """Imite fut_actif.tag (un gestionnaire avec .all()). / Mimics fut_actif.tag."""

    def __init__(self, noms):
        self.noms = noms

    def all(self):
        return [SimpleNamespace(name=nom) for nom in self.noms]


def _tireuse_fictive(couleur="#8b5cf6", avec_fut=True):
    """
    Tireuse en mémoire, sans base de données, pour tester le rendu des templates.
    / In-memory tap, no database, to test template rendering.
    """
    fut = None
    prix_litre = Decimal("0")
    if avec_fut:
        fut = SimpleNamespace(
            name="Ramberte",
            couleur_fond_pos=couleur,
            tag=_TagsFictifs(["Blanche", "4,4°"]),
            long_description="<p>Fraîche.</p>",
            short_description="Brasserie de la Loire",
            img=None,
        )
        prix_litre = Decimal("15.00")
    return SimpleNamespace(
        uuid=uuid.uuid4(),
        nom_tireuse="Tireuse test rendu",
        enabled=True,
        fut_actif=fut,
        liquid_label="Ramberte" if avec_fut else "Liquide",
        prix_litre=prix_litre,
        prix_verre_25cl=prix_litre * Decimal("0.25"),
        reservoir_ml=Decimal("10000"),
        reservoir_max_ml=20000.0,
        reservoir_illimite=False,
    )


class TestRenduKiosk:
    """Le template pose les bonnes variables et gère l'absence de fût."""

    def test_05_detail_pose_la_couleur_du_fut(self):
        """Avec une couleur de fût, le <head> pose --tireuse-accent (texte toujours blanc)."""
        tireuse = _tireuse_fictive(couleur="#884dff")
        html = render_to_string(
            "controlvanne/kiosk_detail.html",
            {"tireuse": tireuse, "config": None, "slug_focus": str(tireuse.uuid)},
        )
        assert "--tireuse-accent: #884dff;" in html
        assert "--tireuse-accent-ink" not in html

    def test_06_veille_sans_fut_affiche_aucun_fut(self):
        """Sans fût actif : écran « Aucun fût branché », pas d'invitation à badger."""
        tireuse = _tireuse_fictive(avec_fut=False)
        html = render_to_string(
            "controlvanne/kiosk_detail.html",
            {"tireuse": tireuse, "config": None, "slug_focus": str(tireuse.uuid)},
        )
        assert 'data-testid="tireuse-sans-fut"' in html
        assert "present-hint" not in html

    def test_07_chaque_vignette_porte_l_accent_de_son_fut(self):
        """Dans la liste, chaque vignette pose l'accent de son propre fût."""
        tireuse_violette = _tireuse_fictive(couleur="#884dff")
        tireuse_verte = _tireuse_fictive(couleur="#228747")
        html = render_to_string(
            "controlvanne/kiosk_list.html",
            {"becs": [tireuse_violette, tireuse_verte], "config": None},
        )
        assert "--tireuse-accent: #884dff;" in html
        assert "--tireuse-accent: #228747;" in html


# ─────────────────────────────────────────────────────────────────────
# Calibration / Calibration
# ─────────────────────────────────────────────────────────────────────


NOM_TIREUSE_CALIBRATION = "Tireuse calibration test"


@pytest.fixture
def tireuse_calibration(tenant):
    """
    Tireuse désactivée (mode maintenance), avec un débitmètre à 6,5 et un
    versement de maintenance de 500 ml en attente de saisie.
    Nettoyée après le test (base dev partagée, pas de rollback).
    / Disabled tap with a 6.5 flow meter and one pending 500 ml pour.
    """
    with tenant_context(tenant):
        from controlvanne.models import Debimetre, RfidSession, TireuseBec
        from django.utils import timezone
        from laboutik.models import PointDeVente, Terminal

        # Restes d'un run précédent (le signal crée un PointDeVente et un
        # Terminal au même nom, qui ne partent pas avec la tireuse)
        # / Leftovers from a previous run (signal-created POS and Terminal)
        TireuseBec.objects.filter(nom_tireuse=NOM_TIREUSE_CALIBRATION).delete()
        PointDeVente.objects.filter(name=NOM_TIREUSE_CALIBRATION).delete()
        Terminal.objects.filter(name=NOM_TIREUSE_CALIBRATION).delete()
        Debimetre.objects.filter(name="Débitmètre calibration test").delete()

        debimetre = Debimetre.objects.create(
            name="Débitmètre calibration test",
            flow_calibration_factor=6.5,
        )
        tireuse = TireuseBec.objects.create(
            nom_tireuse=NOM_TIREUSE_CALIBRATION,
            enabled=False,
            debimetre=debimetre,
        )
        maintenant = timezone.now()
        versement = RfidSession.objects.create(
            uid="CALIBTST",
            tireuse_bec=tireuse,
            authorized=True,
            is_maintenance=True,
            started_at=maintenant,
            ended_at=maintenant,
            volume_delta_ml=Decimal("500.00"),
        )

    yield SimpleNamespace(tireuse=tireuse, debimetre=debimetre, versement=versement)

    with tenant_context(tenant):
        RfidSession.objects.filter(tireuse_bec=tireuse).delete()
        TireuseBec.objects.filter(pk=tireuse.pk).delete()
        PointDeVente.objects.filter(name=NOM_TIREUSE_CALIBRATION).delete()
        Terminal.objects.filter(name=NOM_TIREUSE_CALIBRATION).delete()
        Debimetre.objects.filter(pk=debimetre.pk).delete()


class TestCalibration:
    """Page, validation et application du facteur de calibration."""

    def test_08_serializer_refuse_un_volume_negatif_ou_vide(self):
        """Volume négatif, nul, non numérique ou vide → invalide."""
        from controlvanne.calibration_views import VolumeReelSerializer

        for valeur_incorrecte in ["-5", "0", "abc", ""]:
            validation = VolumeReelSerializer(
                data={"volume_reel_ml": valeur_incorrecte}
            )
            assert not validation.is_valid(), valeur_incorrecte

        assert VolumeReelSerializer(data={"volume_reel_ml": "487"}).is_valid()

    def test_09_page_de_calibration_repond(self, admin_client, tireuse_calibration):
        """La page de calibration s'affiche (200) avec la zone des versements."""
        reponse = admin_client.get(
            f"/controlvanne/calibration/{tireuse_calibration.tireuse.uuid}/"
        )
        assert reponse.status_code == 200
        assert 'data-testid="calibration-zone-versements"' in reponse.content.decode()

    def test_10_nouvelle_serie_redirige_avec_l_heure_du_serveur(
        self, admin_client, tireuse_calibration
    ):
        """?nouvelle_serie=1 → redirection vers ?depuis=<heure du serveur>."""
        reponse = admin_client.get(
            f"/controlvanne/calibration/{tireuse_calibration.tireuse.uuid}/?nouvelle_serie=1"
        )
        assert reponse.status_code == 302
        assert "?depuis=" in reponse["Location"]

    def test_11_volume_invalide_renvoie_422_sans_rien_enregistrer(
        self, admin_client, tireuse_calibration, tenant
    ):
        """Un volume négatif → 422 avec le message, facteur inchangé."""
        versement = tireuse_calibration.versement
        reponse = admin_client.post(
            f"/controlvanne/calibration/{tireuse_calibration.tireuse.uuid}/serie/",
            data={f"vol_{versement.pk}": "-20", "depuis": ""},
        )
        assert reponse.status_code == 422
        assert 'data-testid="calibration-erreur"' in reponse.content.decode()

        with schema_context(tenant.schema_name):
            tireuse_calibration.debimetre.refresh_from_db()
            assert tireuse_calibration.debimetre.flow_calibration_factor == 6.5

    def test_12_aucun_volume_saisi_renvoie_422(self, admin_client, tireuse_calibration):
        """Formulaire vide → 422 « Saisissez au moins un volume »."""
        reponse = admin_client.post(
            f"/controlvanne/calibration/{tireuse_calibration.tireuse.uuid}/serie/",
            data={"depuis": ""},
        )
        assert reponse.status_code == 422

    def test_13_versement_ignore_n_est_pas_compte(
        self, admin_client, tireuse_calibration
    ):
        """Case « ignorer » cochée → le volume saisi n'est pas pris en compte (422)."""
        versement = tireuse_calibration.versement
        reponse = admin_client.post(
            f"/controlvanne/calibration/{tireuse_calibration.tireuse.uuid}/serie/",
            data={
                f"vol_{versement.pk}": "480",
                f"ignorer_{versement.pk}": "1",
                "depuis": "",
            },
        )
        assert reponse.status_code == 422

    def test_14_volume_valide_applique_le_facteur(
        self, admin_client, tireuse_calibration, tenant
    ):
        """500 ml mesurés, 480 ml dans le verre → facteur 6,5 × 500/480 = 6,7708."""
        versement = tireuse_calibration.versement
        reponse = admin_client.post(
            f"/controlvanne/calibration/{tireuse_calibration.tireuse.uuid}/serie/",
            data={f"vol_{versement.pk}": "480", "depuis": ""},
        )
        assert reponse.status_code == 200
        assert 'data-testid="calibration-serie-result"' in reponse.content.decode()

        with schema_context(tenant.schema_name):
            tireuse_calibration.debimetre.refresh_from_db()
            assert tireuse_calibration.debimetre.flow_calibration_factor == 6.7708
            versement.refresh_from_db()
            assert versement.volume_reel_ml == Decimal("480.00")


class TestAccesCalibration:
    """
    La calibration est réservée aux admins du lieu (audit, point 1.5).
    is_staff est un drapeau global : il ne suffit plus.
    / Calibration is for venue admins only; is_staff alone no longer works.
    """

    def test_19_visiteur_non_connecte_va_a_la_connexion(self, tireuse_calibration):
        """Pas connecté → redirection vers la page de connexion."""
        from django.test import Client as DjangoClient

        visiteur = DjangoClient(HTTP_HOST="lespass.tibillet.localhost")
        reponse = visiteur.get(
            f"/controlvanne/calibration/{tireuse_calibration.tireuse.uuid}/"
        )
        assert reponse.status_code == 302

    def test_20_staff_qui_n_est_pas_admin_du_lieu_est_refuse(self, tireuse_calibration):
        """Un compte is_staff qui n'administre pas ce lieu → 403, lecture et écriture."""
        from django.test import Client as DjangoClient

        from AuthBillet.models import TibilletUser

        email = "test-calibration-staff-autre-lieu@example.org"
        staff_d_un_autre_lieu, _created = TibilletUser.objects.get_or_create(
            email=email, defaults={"username": email}
        )
        staff_d_un_autre_lieu.is_staff = True
        staff_d_un_autre_lieu.is_active = True
        staff_d_un_autre_lieu.save()
        staff_d_un_autre_lieu.client_admin.clear()

        navigateur = DjangoClient(HTTP_HOST="lespass.tibillet.localhost")
        navigateur.force_login(staff_d_un_autre_lieu)
        uuid_tireuse = tireuse_calibration.tireuse.uuid
        assert (
            navigateur.get(f"/controlvanne/calibration/{uuid_tireuse}/").status_code
            == 403
        )
        assert (
            navigateur.get(
                f"/controlvanne/calibration/{uuid_tireuse}/sessions/"
            ).status_code
            == 403
        )
        versement = tireuse_calibration.versement
        reponse_envoi = navigateur.post(
            f"/controlvanne/calibration/{uuid_tireuse}/serie/",
            data={f"vol_{versement.pk}": "480", "depuis": ""},
        )
        assert reponse_envoi.status_code == 403

    def test_21_debitmetre_partage_est_signale(
        self, admin_client, tireuse_calibration, tenant
    ):
        """Si une autre tireuse utilise le même débitmètre, la page le signale."""
        from laboutik.models import PointDeVente, Terminal

        from controlvanne.models import TireuseBec

        nom_autre_tireuse = "Tireuse meme debitmetre test"
        with tenant_context(tenant):
            TireuseBec.objects.filter(nom_tireuse=nom_autre_tireuse).delete()
            PointDeVente.objects.filter(name=nom_autre_tireuse).delete()
            Terminal.objects.filter(name=nom_autre_tireuse).delete()
            autre_tireuse = TireuseBec.objects.create(
                nom_tireuse=nom_autre_tireuse,
                enabled=False,
                debimetre=tireuse_calibration.debimetre,
            )
        try:
            reponse = admin_client.get(
                f"/controlvanne/calibration/{tireuse_calibration.tireuse.uuid}/"
            )
            contenu = reponse.content.decode()
            assert 'data-testid="calibration-debitmetre-partage"' in contenu
            assert nom_autre_tireuse in contenu
        finally:
            with tenant_context(tenant):
                TireuseBec.objects.filter(pk=autre_tireuse.pk).delete()
                PointDeVente.objects.filter(name=nom_autre_tireuse).delete()
                Terminal.objects.filter(name=nom_autre_tireuse).delete()


# ─────────────────────────────────────────────────────────────────────
# Formulaire des fûts / Keg form
# ─────────────────────────────────────────────────────────────────────


class TestCouleurDuFut:
    """La couleur d'accent du fût doit être un code #rrggbb."""

    def test_15_couleur_hors_format_refusee(self):
        """« rouge » est refusé ; « #8B5CF6 » est accepté et mis en minuscules."""
        from Administration.admin.products import FutProductForm

        formulaire = FutProductForm.__new__(FutProductForm)
        formulaire.cleaned_data = {"couleur_fond_pos": "rouge"}
        with pytest.raises(Exception):
            formulaire.clean_couleur_fond_pos()

        formulaire.cleaned_data = {"couleur_fond_pos": "#8B5CF6"}
        assert formulaire.clean_couleur_fond_pos() == "#8b5cf6"

        formulaire.cleaned_data = {"couleur_fond_pos": ""}
        assert formulaire.clean_couleur_fond_pos() == ""


# ─────────────────────────────────────────────────────────────────────
# Rechargement du kiosk quand le fût change / Kiosk reload on keg change
# ─────────────────────────────────────────────────────────────────────


class _CanalFictif:
    """
    Remplace le channel layer : garde les messages envoyés au lieu de les pousser.
    / Replaces the channel layer: keeps sent messages instead of pushing them.
    """

    def __init__(self):
        self.messages_envoyes = []

    async def group_send(self, groupe, message):
        self.messages_envoyes.append((groupe, message["payload"]))

    def demandes_de_rechargement(self, tireuse):
        """Groupes ayant reçu un kiosk_reload pour cette tireuse."""
        groupes = []
        for groupe, payload in self.messages_envoyes:
            if payload.get("kiosk_reload") and payload.get("tireuse_bec_uuid") == str(
                tireuse.uuid
            ):
                groupes.append(groupe)
        return groupes


NOM_TIREUSE_RECHARGEMENT = "Tireuse rechargement test"


@pytest.fixture
def tireuse_et_deux_futs(tenant):
    """
    Une tireuse avec un fût A, et un fût B prêt à être branché.
    Nettoyés après le test (base dev partagée, pas de rollback).
    / A tap with keg A, and a keg B ready to be plugged in.
    """
    with tenant_context(tenant):
        from BaseBillet.models import Product
        from controlvanne.models import TireuseBec
        from laboutik.models import PointDeVente, Terminal

        TireuseBec.objects.filter(nom_tireuse=NOM_TIREUSE_RECHARGEMENT).delete()
        PointDeVente.objects.filter(name=NOM_TIREUSE_RECHARGEMENT).delete()
        Terminal.objects.filter(name=NOM_TIREUSE_RECHARGEMENT).delete()
        Product.objects.filter(
            name__in=["Fût rechargement A", "Fût rechargement B"]
        ).delete()

        fut_a = Product.objects.create(
            name="Fût rechargement A", categorie_article=Product.FUT
        )
        fut_b = Product.objects.create(
            name="Fût rechargement B", categorie_article=Product.FUT
        )
        tireuse = TireuseBec.objects.create(
            nom_tireuse=NOM_TIREUSE_RECHARGEMENT, enabled=True, fut_actif=fut_a
        )

    yield SimpleNamespace(tireuse=tireuse, fut_a=fut_a, fut_b=fut_b)

    with tenant_context(tenant):
        TireuseBec.objects.filter(pk=tireuse.pk).delete()
        PointDeVente.objects.filter(name=NOM_TIREUSE_RECHARGEMENT).delete()
        Terminal.objects.filter(name=NOM_TIREUSE_RECHARGEMENT).delete()
        Product.objects.filter(pk__in=[fut_a.pk, fut_b.pk]).delete()


class TestRechargementDuKiosk:
    """Le kiosk recharge sa page quand le fût branché change ou est modifié."""

    def test_16_changer_le_fut_recharge_les_kiosks(self, tireuse_et_deux_futs, tenant):
        """Brancher le fût B → kiosk_reload sur l'écran de la tireuse et sur la liste."""
        from unittest import mock

        canal = _CanalFictif()
        tireuse = tireuse_et_deux_futs.tireuse
        with (
            tenant_context(tenant),
            mock.patch("controlvanne.groupes_ws.get_channel_layer", return_value=canal),
        ):
            tireuse.fut_actif = tireuse_et_deux_futs.fut_b
            tireuse.save()

        # Groupes nommés PAR LIEU (controlvanne/groupes_ws.py, audit point 1.2)
        # / Groups named PER VENUE
        from controlvanne.groupes_ws import groupe_de_la_tireuse, groupe_de_tout_le_lieu

        groupes = canal.demandes_de_rechargement(tireuse)
        assert groupe_de_la_tireuse(tenant.uuid, tireuse.uuid) in groupes
        assert groupe_de_tout_le_lieu(tenant.uuid) in groupes
        # Plus aucun envoi vers l'ancien groupe commun à tous les lieux
        # / No more sends to the old group shared by all venues
        assert "rfid_state.all" not in groupes

    def test_17_modifier_le_fut_branche_recharge_les_kiosks(
        self, tireuse_et_deux_futs, tenant
    ):
        """Changer la couleur du fût branché → kiosk_reload pour sa tireuse."""
        from unittest import mock

        from BaseBillet.models import FutProduct

        canal = _CanalFictif()
        with (
            tenant_context(tenant),
            mock.patch("controlvanne.groupes_ws.get_channel_layer", return_value=canal),
        ):
            # Comme l'admin des fûts : on enregistre le modèle proxy FutProduct
            # / Like the keg admin: the FutProduct proxy is saved
            fut_vu_par_l_admin = FutProduct.objects.get(
                pk=tireuse_et_deux_futs.fut_a.pk
            )
            fut_vu_par_l_admin.couleur_fond_pos = "#884dff"
            fut_vu_par_l_admin.save()

        assert canal.demandes_de_rechargement(tireuse_et_deux_futs.tireuse)

    def test_18_mise_a_jour_du_reservoir_ne_recharge_pas(
        self, tireuse_et_deux_futs, tenant
    ):
        """Le niveau du fût change à chaque tirage : snapshot seulement, pas de rechargement."""
        from unittest import mock

        canal = _CanalFictif()
        tireuse = tireuse_et_deux_futs.tireuse
        with (
            tenant_context(tenant),
            mock.patch("controlvanne.groupes_ws.get_channel_layer", return_value=canal),
        ):
            tireuse.reservoir_ml = Decimal("1234.00")
            tireuse.save(update_fields=["reservoir_ml"])

        assert canal.demandes_de_rechargement(tireuse) == []
        assert canal.messages_envoyes, "un snapshot doit quand même partir"
