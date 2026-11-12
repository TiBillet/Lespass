"""
Observatoire des instances : le calcul nocturne et la page du superadmin.
/ Instance observatory: the nightly computation and the superadmin page.

LOCALISATION : tests/pytest/test_observatoire.py
Spec : TECH_DOC/SESSIONS/OBSERVATOIRE/SPEC.md (section 8).

CE QUE CES TESTS PROTEGENT
1. Les chiffres d'argent viennent des clotures comptables, lues au bon mois :
   mensuelles d'abord, journalieres ensuite, jamais la J « reprise ».
2. Les compteurs hors clotures (billets scannes, usagers) sont justes.
3. Un lieu en erreur ne bloque pas les autres ; un calcul rate n'ecrase pas le cache.
4. La page n'est lisible QUE par le superadmin, en GET seulement.
/ Money comes from closures; other counters are right; failures are contained;
  the page is superadmin-only and read-only.

Tout se passe dans un lieu de test (`FastTenantTestCase`) : chaque test est annule
a la fin, y compris les lignes du schema public (lieux, comptes, SEOCache).
/ Runs in a test venue; every test is rolled back, public rows included.
"""

import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser
from BaseBillet.models import Event, PaymentMethod, Reservation, SaleOrigin, Ticket
from BaseBillet.models_vente import Vente
from comptabilite.models import ClotureCaisse
from Customers.models import Client
from seo import observatoire
from fedow_core.models import Transaction
from seo.models import SEOCache

FUSEAU_DU_LIEU = "Europe/Paris"


def identifiant_unique():
    return uuid.uuid4().hex[:10]


def debut_d_un_mois(annee, mois):
    """Le 1er du mois a 00:00, heure locale. / First day of the month, local time."""
    return timezone.make_aware(datetime(annee, mois, 1))


def rapport_de_cloture(
    total_ttc=0,
    total_caisse=0,
    recharges_par_moyen=None,
    billets_par_tarif=None,
    adhesions=None,
    reprise=False,
):
    """
    Un `rapport_json` de cloture, avec la MEME forme que celui ecrit par
    comptabilite/rapport.py (relevee sur une vraie cloture de dev).
    Seules les cles lues par l'observatoire sont remplies.
    / A closure report with the same shape as comptabilite/rapport.py writes.

    :param billets_par_tarif: liste de (quantite, total_ttc) pour un evenement
    :param adhesions: liste de (quantite, total_ttc), un produit chacun
    """
    en_tete = {"fuseau_horaire": FUSEAU_DU_LIEU, "niveau": "M"}
    if reprise:
        en_tete["reprise"] = True

    par_tarif = {}
    for quantite, total in billets_par_tarif or []:
        par_tarif[str(uuid.uuid4())] = {
            "nom": "Plein tarif",
            "quantite": f"{quantite}.000000",
            "total_ttc_en_centimes": total,
        }
    billets = {}
    if par_tarif:
        billets[str(uuid.uuid4())] = {"nom": "Concert", "par_tarif": par_tarif}

    detail_des_adhesions = {}
    for quantite, total in adhesions or []:
        detail_des_adhesions[str(uuid.uuid4())] = {
            "nom": "Adhésion",
            "quantite": f"{quantite}.000000",
            "total_ttc_en_centimes": total,
        }

    par_origine = {}
    if total_caisse:
        par_origine["LB"] = {"total_ttc_en_centimes": total_caisse}

    par_moyen = {}
    for code_du_moyen, total in (recharges_par_moyen or {}).items():
        par_moyen[code_du_moyen] = {
            "libelle": code_du_moyen,
            "total_en_centimes": total,
        }

    return {
        "en_tete": en_tete,
        "chiffre_affaires": {
            "total_ttc_en_centimes": total_ttc,
            "par_origine": par_origine,
        },
        "annexe": {
            "recharges_et_cartes": {
                "recharges_encaissees": {"par_moyen": par_moyen, "total_en_centimes": 0}
            }
        },
        "detail": {"billets": billets, "adhesions": detail_des_adhesions},
    }


class TestObservatoire(FastTenantTestCase):
    """L'observatoire, dans un lieu de test. / The observatory, in a test venue."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_observatoire"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-observatoire.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = "Test Observatoire"

    def setUp(self):
        # Re-poser le search_path apres le rollback du test precedent.
        # / Re-set search_path after the previous test's rollback.
        connection.set_tenant(self.tenant)
        self.numero_de_cloture = 0
        # Une periode de 24 mois qui finit au mois courant, comme la commande.
        # / A 24-month period ending this month, like the command.
        self.mois_de_la_periode = observatoire.liste_des_mois(24)
        self.premier_jour = observatoire.premier_jour_de_la_periode(
            self.mois_de_la_periode
        )

    # ------------------------------------------------------------------
    # Outils / Tools
    # ------------------------------------------------------------------

    def creer_une_cloture(self, niveau, debut, fin, rapport):
        self.numero_de_cloture += 1
        return ClotureCaisse.objects.create(
            niveau=niveau,
            numero_sequentiel=self.numero_de_cloture,
            datetime_debut=debut,
            datetime_fin=fin,
            rapport_json=rapport,
        )

    def deux_mois_passes(self):
        """
        Les debuts de M-3, M-2 et M-1 (M = mois courant), en heure locale.
        / Starts of the three previous months, local time.
        """
        aujourd_hui = timezone.localdate()
        debuts = []
        annee, mois = aujourd_hui.year, aujourd_hui.month
        for _numero in range(3):
            mois -= 1
            if mois == 0:
                mois, annee = 12, annee - 1
            debuts.append(debut_d_un_mois(annee, mois))
        debuts.reverse()
        return debuts

    def lieu_de_test_seul(self):
        """
        La liste des lieux du calcul, reduite au lieu de test, avec son annotation
        `nombre_de_comptes_admin` (comme la vraie requete). La base de dev contient
        d'autres lieux : le calcul ne doit lire que celui-ci.
        / The venue list reduced to the test venue, annotated like the real query.
        """
        lieux_annotes = observatoire.lieux_du_reseau()
        return [lieu for lieu in lieux_annotes if lieu.pk == self.tenant.pk]

    def creer_un_utilisateur(self, superadmin=False):
        return TibilletUser.objects.create(
            email=f"obs-{identifiant_unique()}@tibillet.localhost",
            username=f"obs-{identifiant_unique()}",
            espece=TibilletUser.TYPE_HUM,
            is_active=True,
            is_superuser=superadmin,
        )

    # ------------------------------------------------------------------
    # 1. Les clotures / Closures
    # ------------------------------------------------------------------

    def test_une_cloture_mensuelle_donne_l_argent_et_les_ventes_de_son_mois(self):
        """
        Une M donne le CA, la caisse, les recharges en ligne et sur place, les
        billets et les adhesions, rangés au mois de la cloture.
        / An M closure gives revenue, POS, top-ups, tickets and memberships for its month.
        """
        debut_m3, debut_m2, debut_m1 = self.deux_mois_passes()
        self.creer_une_cloture(
            ClotureCaisse.NIVEAU_MENSUEL,
            debut_m2,
            debut_m1,
            rapport_de_cloture(
                total_ttc=18200,
                total_caisse=5000,
                recharges_par_moyen={"SN": 3000, "CA": 1000, "CC": 500},
                billets_par_tarif=[(3, 6000), (1, 0)],
                adhesions=[(2, 6000)],
            ),
        )

        compteurs_par_mois, _points_de_vente = observatoire.activite_du_lieu(
            self.premier_jour
        )
        compteurs = compteurs_par_mois[debut_m2.strftime("%Y-%m")]

        assert compteurs["ca_total"] == 18200
        assert compteurs["ca_caisse"] == 5000
        assert compteurs["ca_billetterie"] == 6000
        assert compteurs["ca_adhesions"] == 6000
        assert compteurs["recharges_ligne"] == 3000
        assert compteurs["recharges_place"] == 1500
        assert compteurs["inscriptions"] == 4
        assert compteurs["adhesions"] == 2

    def test_une_journaliere_apres_la_derniere_mensuelle_compte_dans_son_mois(self):
        """
        Le mois sans M (le mois en cours) prend la somme de ses J.
        Une J d'avant la derniere M n'est pas comptee deux fois.
        / The month without an M sums its J; a J before the last M is not counted twice.
        """
        debut_m3, debut_m2, debut_m1 = self.deux_mois_passes()
        self.creer_une_cloture(
            ClotureCaisse.NIVEAU_MENSUEL,
            debut_m1,
            debut_m1 + timedelta(days=28),
            rapport_de_cloture(total_ttc=10000),
        )
        # Une J deja comprise dans la M : ne doit pas s'ajouter.
        # / A J already inside the M: must not be added.
        self.creer_une_cloture(
            ClotureCaisse.NIVEAU_JOURNALIER,
            debut_m1,
            debut_m1 + timedelta(days=1),
            rapport_de_cloture(total_ttc=999),
        )
        # Deux J du mois en cours.
        # / Two J of the current month.
        maintenant = timezone.now()
        self.creer_une_cloture(
            ClotureCaisse.NIVEAU_JOURNALIER,
            maintenant - timedelta(hours=3),
            maintenant - timedelta(hours=2),
            rapport_de_cloture(total_ttc=700),
        )
        self.creer_une_cloture(
            ClotureCaisse.NIVEAU_JOURNALIER,
            maintenant - timedelta(hours=2),
            maintenant - timedelta(hours=1),
            rapport_de_cloture(total_ttc=300),
        )

        compteurs_par_mois, _points_de_vente = observatoire.activite_du_lieu(
            self.premier_jour
        )

        assert compteurs_par_mois[debut_m1.strftime("%Y-%m")]["ca_total"] == 10000
        mois_de_la_fin = timezone.localtime(maintenant - timedelta(hours=1)).strftime(
            "%Y-%m"
        )
        assert compteurs_par_mois[mois_de_la_fin]["ca_total"] == 1000

    def test_la_journaliere_de_reprise_n_est_jamais_comptee(self):
        """
        La J « reprise » couvre tout l'historique d'avant la bascule : la compter
        ferait un pic faux. Une J ordinaire, sans cle « reprise », reste comptee.
        / The "reprise" J is never counted; an ordinary J (no "reprise" key) is.
        """
        maintenant = timezone.now()
        self.creer_une_cloture(
            ClotureCaisse.NIVEAU_JOURNALIER,
            maintenant - timedelta(hours=4),
            maintenant - timedelta(hours=3),
            rapport_de_cloture(total_ttc=5_000_000, reprise=True),
        )
        self.creer_une_cloture(
            ClotureCaisse.NIVEAU_JOURNALIER,
            maintenant - timedelta(hours=3),
            maintenant - timedelta(hours=2),
            rapport_de_cloture(total_ttc=400),
        )

        compteurs_par_mois, _points_de_vente = observatoire.activite_du_lieu(
            self.premier_jour
        )

        mois_de_la_fin = timezone.localtime(maintenant - timedelta(hours=2)).strftime(
            "%Y-%m"
        )
        assert compteurs_par_mois[mois_de_la_fin]["ca_total"] == 400

    def test_la_mensuelle_du_mois_le_plus_ancien_compte_meme_a_l_est_du_serveur(self):
        """
        Lieu en Europe/Paris, serveur en UTC : la M du mois le plus ancien commence
        la veille au soir en UTC, avant le premier jour de la periode. Elle compte.
        / Venue in Europe/Paris, server in UTC: the oldest M starts the evening before
          in UTC. It must be counted.
        """
        from zoneinfo import ZoneInfo

        fuseau_de_paris = ZoneInfo(FUSEAU_DU_LIEU)
        mois_le_plus_ancien = self.mois_de_la_periode[0]
        annee, mois = int(mois_le_plus_ancien[:4]), int(mois_le_plus_ancien[5:7])
        debut_a_paris = datetime(annee, mois, 1, tzinfo=fuseau_de_paris)
        fin_a_paris = datetime(
            annee + (mois == 12), mois % 12 + 1, 1, tzinfo=fuseau_de_paris
        )
        self.creer_une_cloture(
            ClotureCaisse.NIVEAU_MENSUEL,
            debut_a_paris,
            fin_a_paris,
            rapport_de_cloture(total_ttc=100000),
        )

        compteurs_par_mois, _points_de_vente = observatoire.activite_du_lieu(
            self.premier_jour
        )

        assert compteurs_par_mois[mois_le_plus_ancien]["ca_total"] == 100000

    def test_la_journaliere_a_cheval_sur_la_fin_de_la_mensuelle_n_est_pas_comptee_deux_fois(
        self,
    ):
        """
        La J de la soiree du 31 finit le 1er au matin : ses ventes sont deja dans la M.
        Elle ne s'ajoute pas au mois suivant.
        / The J of the 31st evening ends on the 1st: already in the M, not added again.
        """
        debut_m3, debut_m2, debut_m1 = self.deux_mois_passes()
        self.creer_une_cloture(
            ClotureCaisse.NIVEAU_MENSUEL,
            debut_m2,
            debut_m1,
            rapport_de_cloture(total_ttc=10000),
        )
        self.creer_une_cloture(
            ClotureCaisse.NIVEAU_JOURNALIER,
            debut_m1 - timedelta(hours=5),
            debut_m1 + timedelta(hours=3),
            rapport_de_cloture(total_ttc=777),
        )

        compteurs_par_mois, _points_de_vente = observatoire.activite_du_lieu(
            self.premier_jour
        )

        assert compteurs_par_mois[debut_m2.strftime("%Y-%m")]["ca_total"] == 10000
        assert debut_m1.strftime("%Y-%m") not in compteurs_par_mois

    # ------------------------------------------------------------------
    # 2. Hors clotures / Outside closures
    # ------------------------------------------------------------------

    def test_seuls_les_billets_scannes_sont_comptes_au_mois_de_l_evenement(self):
        """
        Une reservation a 3 billets dont 2 scannes donne billets_scannes = 2, au
        mois de l'evenement.
        / A 3-ticket booking with 2 scanned gives 2, in the event's month.
        """
        date_de_l_evenement = timezone.now() - timedelta(days=1)
        evenement = Event.objects.create(
            name=f"TEST_obs evenement {identifiant_unique()}",
            datetime=date_de_l_evenement,
        )
        reservation = Reservation.objects.create(
            user_commande=self.creer_un_utilisateur(), event=evenement
        )
        Ticket.objects.create(reservation=reservation, status=Ticket.SCANNED)
        Ticket.objects.create(reservation=reservation, status=Ticket.SCANNED)
        Ticket.objects.create(reservation=reservation, status=Ticket.NOT_SCANNED)

        compteurs_par_mois, _points_de_vente = observatoire.activite_du_lieu(
            self.premier_jour
        )

        mois_de_l_evenement = timezone.localtime(date_de_l_evenement).strftime("%Y-%m")
        assert compteurs_par_mois[mois_de_l_evenement]["billets_scannes"] == 2
        assert compteurs_par_mois[mois_de_l_evenement]["evenements"] == 1

    def test_un_client_qui_achete_deux_fois_compte_pour_un_usager(self):
        """
        Usagers = clients DISTINCTS des ventes reglees du mois.
        / Users = DISTINCT clients of the month's settled sales.
        """
        from fabriques_vente import creer_tarif_vendu, fabriquer_vente_encaissee

        client = self.creer_un_utilisateur()
        tarif_vendu = creer_tarif_vendu(
            nom="Article observatoire", prix_en_euros="5.00"
        )
        for _numero in range(2):
            fabriquer_vente_encaissee(
                origine=SaleOrigin.ADMIN,
                articles=[
                    {
                        "pricesold": tarif_vendu,
                        "quantite": Decimal("1"),
                        "prix_unitaire": 500,
                        "taux_tva": Decimal("0"),
                    }
                ],
                reglements=[{"moyen": PaymentMethod.CASH, "montant": 500}],
                client=client,
            )
        assert (
            Vente.objects.filter(client=client, statut=Vente.Statut.REGLEE).count() == 2
        )

        compteurs_par_mois, _points_de_vente = observatoire.activite_du_lieu(
            self.premier_jour
        )

        mois_courant = timezone.localtime().strftime("%Y-%m")
        assert compteurs_par_mois[mois_courant]["usagers"] == 1

    # ------------------------------------------------------------------
    # 3. Le schema public / The public schema
    # ------------------------------------------------------------------

    def test_les_admins_du_lieu_sont_comptes(self):
        """La requete des lieux compte les admins de chaque lieu. / Admins are counted."""
        for _numero in range(2):
            self.creer_un_utilisateur().client_admin.add(self.tenant)

        lieux = observatoire.lieux_du_reseau()

        lieu_de_test = [lieu for lieu in lieux if lieu.pk == self.tenant.pk][0]
        assert lieu_de_test.nombre_de_comptes_admin == 2

    def test_un_emplacement_en_attente_n_est_pas_lu(self):
        """
        Un emplacement WAITING_CONFIG n'est jamais lu (interblocage avec cron_morning).
        / A WAITING_CONFIG slot is never read.
        """
        Client.objects.filter(pk=self.tenant.pk).update(categorie=Client.WAITING_CONFIG)

        lieux = observatoire.lieux_du_reseau()

        assert self.tenant.pk not in [lieu.pk for lieu in lieux]

    # ------------------------------------------------------------------
    # 4. Robustesse / Robustness
    # ------------------------------------------------------------------

    def test_un_lieu_en_erreur_n_empeche_pas_les_autres(self):
        """
        Le 1er lieu plante, le 2e est lu : le bilan note 1 erreur et 1 lieu lu.
        / The first venue fails, the second is read.
        """
        vraie_activite = observatoire.activite_du_lieu
        appels = {"nombre": 0}

        def activite_qui_plante_au_premier_appel(premier_jour):
            appels["nombre"] += 1
            if appels["nombre"] == 1:
                raise ValueError("lieu cassé")
            return vraie_activite(premier_jour)

        with mock.patch.object(
            observatoire, "lieux_du_reseau", return_value=self.lieu_de_test_seul() * 2
        ):
            with mock.patch.object(
                observatoire,
                "activite_du_lieu",
                side_effect=activite_qui_plante_au_premier_appel,
            ):
                donnees = observatoire.calculer_observatoire_du_reseau(
                    nombre_de_mois=13, journal=lambda texte: None
                )

        assert donnees["bilan"]["lieux_lus"] == 1
        assert len(donnees["bilan"]["erreurs"]) == 1

    def test_un_calcul_sans_aucun_lieu_lu_n_ecrase_pas_le_cache(self):
        """
        Aucun lieu lu : la commande echoue et le dernier bon calcul reste.
        / No venue read: the command fails and the last good computation stays.
        """
        SEOCache.objects.update_or_create(
            cache_type=SEOCache.OBSERVATOIRE,
            tenant=None,
            defaults={"data": {"marque": "bon calcul"}},
        )

        with mock.patch.object(observatoire, "lieux_du_reseau", return_value=[]):
            with pytest.raises(CommandError):
                call_command("refresh_observatoire")

        ligne = SEOCache.objects.get(
            cache_type=SEOCache.OBSERVATOIRE, tenant__isnull=True
        )
        assert ligne.data == {"marque": "bon calcul"}

    def test_la_commande_ecrit_le_cache_complet(self):
        """
        La commande ecrit un cache avec le contrat lu par le JS.
        / The command writes a cache with the contract read by the JS.
        """
        with mock.patch.object(
            observatoire, "lieux_du_reseau", return_value=self.lieu_de_test_seul()
        ):
            call_command("refresh_observatoire", mois=13)

        donnees = SEOCache.objects.get(
            cache_type=SEOCache.OBSERVATOIRE, tenant__isnull=True
        ).data
        assert donnees["cles"] == observatoire.CLES_DES_COMPTEURS
        assert len(donnees["mois"]) == 13
        assert donnees["bilan"]["lieux_lus"] == 1
        assert donnees["calcule_par"] == "manage.py"
        ligne_du_lieu = donnees["inst"][0]
        assert ligne_du_lieu[0] == self.tenant.schema_name
        assert len(ligne_du_lieu[6]) == len(observatoire.CLES_DES_COMPTEURS)

    # ------------------------------------------------------------------
    # 5. La page / The page
    # ------------------------------------------------------------------

    def navigateur_connecte(self, utilisateur):
        navigateur = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        navigateur.force_login(utilisateur)
        return navigateur

    def test_un_admin_du_lieu_non_superadmin_recoit_403(self):
        """
        admin_view laisse passer un admin du lieu : c'est la vue qui doit refuser.
        / admin_view lets a venue admin in: the view must refuse.
        """
        admin_du_lieu = self.creer_un_utilisateur()
        admin_du_lieu.client_admin.add(self.tenant)

        reponse = self.navigateur_connecte(admin_du_lieu).get(
            reverse("staff_admin:observatoire")
        )

        assert reponse.status_code == 403

    def test_un_admin_du_lieu_avec_is_staff_recoit_aussi_403(self):
        """`is_staff` ne donne aucun droit sur cette page. / is_staff grants nothing here."""
        admin_du_lieu = self.creer_un_utilisateur()
        admin_du_lieu.is_staff = True
        admin_du_lieu.save()
        admin_du_lieu.client_admin.add(self.tenant)

        reponse = self.navigateur_connecte(admin_du_lieu).get(
            reverse("staff_admin:observatoire")
        )

        assert reponse.status_code == 403

    def test_le_superadmin_voit_la_page(self):
        """
        Le superadmin voit la page, jamais gardee en cache, avec le bloc « depuis le
        debut » et les cartes de Fedow legacy.
        / Superadmin sees it, no-store, with the "since the beginning" block.
        """
        reponse_de_fedow = {
            "recharges_par_asset": [],
            "cartes": {"total": 9123, "liees_a_un_compte": 6000},
        }
        with mock.patch.object(
            observatoire, "lieux_du_reseau", return_value=self.lieu_de_test_seul()
        ):
            with mock.patch.object(
                observatoire,
                "statistiques_de_fedow_legacy",
                return_value=reponse_de_fedow,
            ):
                call_command("refresh_observatoire", mois=13)

        reponse = self.navigateur_connecte(
            self.creer_un_utilisateur(superadmin=True)
        ).get(reverse("staff_admin:observatoire"))

        assert reponse.status_code == 200
        assert "no-store" in reponse["Cache-Control"]
        contenu = reponse.content.decode()
        assert 'id="observatoire-donnees"' in contenu
        assert 'data-testid="observatoire-tuiles"' in contenu
        # La valeur de la tuile, sans ses separateurs de milliers (espace insecable).
        # / The tile value, without its thousands separators.
        tuile_des_cartes = contenu.split('data-testid="observatoire-reseau-cartes"')[1]
        valeur_affichee = tuile_des_cartes.split('class="val">')[1].split("</span>")[0]
        assert re.sub(r"\D", "", valeur_affichee) == "9123"

    def test_un_post_est_refuse_meme_au_superadmin(self):
        """Aucune ecriture : POST repond 405. / No write: POST answers 405."""
        reponse = self.navigateur_connecte(
            self.creer_un_utilisateur(superadmin=True)
        ).post(reverse("staff_admin:observatoire"))

        assert reponse.status_code == 405

    def test_sans_cache_la_page_dit_aucun_calcul_et_ne_calcule_rien(self):
        """
        Cache vide : message « Aucun calcul », et le calcul n'est jamais appele.
        / Empty cache: "no computation" message, and the computation is never called.
        """
        SEOCache.objects.filter(cache_type=SEOCache.OBSERVATOIRE).delete()

        with mock.patch.object(
            observatoire, "calculer_observatoire_du_reseau"
        ) as calcul_espionne:
            reponse = self.navigateur_connecte(
                self.creer_un_utilisateur(superadmin=True)
            ).get(reverse("staff_admin:observatoire"))

        assert reponse.status_code == 200
        assert 'data-testid="observatoire-vide"' in reponse.content.decode()
        calcul_espionne.assert_not_called()
        assert not SEOCache.objects.filter(cache_type=SEOCache.OBSERVATOIRE).exists()


class TestReseauDepuisLeDebut(FastTenantTestCase):
    """
    Le bloc « Le reseau depuis le debut » : totaux cumules pour une presentation.
    / The "network since the beginning" block: cumulative totals.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_observatoire_reseau"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-observatoire-reseau.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = "Test Observatoire Reseau"

    def setUp(self):
        connection.set_tenant(self.tenant)

    def creer_un_utilisateur(self):
        return TibilletUser.objects.create(
            email=f"obs-{identifiant_unique()}@tibillet.localhost",
            username=f"obs-{identifiant_unique()}",
            espece=TibilletUser.TYPE_HUM,
            is_active=True,
        )

    def test_seuls_les_billets_valides_sont_comptes(self):
        """
        Valides = scannes ou non. Un billet annule ne compte pas.
        / Valid = scanned or not. A cancelled ticket does not count.
        """
        evenement = Event.objects.create(
            name=f"TEST_obs {identifiant_unique()}", datetime=timezone.now()
        )
        reservation = Reservation.objects.create(
            user_commande=self.creer_un_utilisateur(), event=evenement
        )
        Ticket.objects.create(reservation=reservation, status=Ticket.SCANNED)
        Ticket.objects.create(reservation=reservation, status=Ticket.NOT_SCANNED)
        Ticket.objects.create(reservation=reservation, status=Ticket.CANCELED)

        totaux = observatoire.totaux_du_lieu_depuis_le_debut()

        assert totaux["billets_valides"] == 2
        assert totaux["billets_scannes"] == 1

    def test_les_heures_de_benevolat_comptent_chaque_inscrit_et_passent_minuit(self):
        """
        Un creneau 21:00 -> 00:00 avec 2 inscrits donne 6 h. Une journee entiere
        (sans horaire) n'est pas comptee.
        / A 21:00 -> 00:00 slot with 2 sign-ups gives 6 h; a whole-day need is not counted.
        """
        import datetime as module_datetime

        from booking.models import (
            BesoinBenevole,
            InscriptionBenevole,
            PlanningBenevole,
            TacheBenevole,
        )

        identifiant = identifiant_unique()
        planning = PlanningBenevole.objects.create(
            name=f"TEST_obs {identifiant}", slug=f"test-obs-{identifiant}"
        )
        tache = TacheBenevole.objects.create(name=f"TEST_obs bar {identifiant}")
        creneau_du_soir = BesoinBenevole.objects.create(
            planning=planning,
            tache=tache,
            date=timezone.localdate(),
            nombre_souhaite=2,
            heure_debut=module_datetime.time(21),
            heure_fin=module_datetime.time(0),
        )
        journee_entiere = BesoinBenevole.objects.create(
            planning=planning,
            tache=tache,
            date=timezone.localdate(),
            nombre_souhaite=2,
        )
        for _numero in range(2):
            InscriptionBenevole.objects.create(
                besoin=creneau_du_soir, user=self.creer_un_utilisateur()
            )
        InscriptionBenevole.objects.create(
            besoin=journee_entiere, user=self.creer_un_utilisateur()
        )

        totaux = observatoire.totaux_du_lieu_depuis_le_debut()

        assert totaux["minutes_de_benevolat"] == 6 * 60

    def test_les_recharges_fed_du_moteur_v2_ne_sont_pas_comptees(self):
        """
        Le FED vit dans Fedow legacy : le compter aussi dans le moteur V2 le
        compterait deux fois. Une monnaie locale (TLF) du moteur V2 est comptee.
        / FED lives in legacy Fedow: counting the V2 copy would count it twice.
        """
        from fedow_core.models import Asset, Wallet
        from fedow_core.services import AssetService

        wallet_du_lieu = Wallet.objects.create(
            name=f"TEST_obs lieu {identifiant_unique()}"
        )
        wallet_d_une_personne = Wallet.objects.create(
            name=f"TEST_obs personne {identifiant_unique()}"
        )
        monnaie_locale = AssetService.creer_asset(
            tenant=self.tenant,
            name=f"TEST_obs locale {identifiant_unique()}",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_du_lieu,
        )
        # Aujourd'hui, Asset.save() refuse un FED local (FEDOW_AUTORISER_ASSET_FED_LOCAL).
        # La garde sautera a la migration : c'est ce cas que le test couvre, en levant
        # le reglage prevu pour les tests d'apres-migration.
        # / Today Asset.save() refuses a local FED; the guard goes away at migration time.
        with override_settings(FEDOW_AUTORISER_ASSET_FED_LOCAL=True):
            monnaie_federee = AssetService.creer_asset(
                tenant=self.tenant,
                name=f"TEST_obs fed {identifiant_unique()}",
                category=Asset.FED,
                currency_code="EUR",
                wallet_origin=wallet_du_lieu,
            )
        for monnaie, montant in [(monnaie_locale, 1500), (monnaie_federee, 9999)]:
            Transaction.objects.create(
                sender=wallet_du_lieu,
                receiver=wallet_d_une_personne,
                asset=monnaie,
                amount=montant,
                action=Transaction.REFILL,
                datetime=timezone.now(),
                tenant=self.tenant,
            )

        recharges = observatoire.recharges_du_moteur_v2()

        categories_lues = [recharge["categorie"] for recharge in recharges]
        assert Asset.FED not in categories_lues
        recharge_locale = [
            recharge
            for recharge in recharges
            if recharge["uuid"] == str(monnaie_locale.uuid)
        ][0]
        assert recharge_locale["total"] == 1500

    def test_le_total_additionne_legacy_et_v2_en_euros_seulement(self):
        """
        Total des recharges = euros de Fedow legacy (FED, TLF) + euros du moteur V2.
        Les heures (TIM) ne s'additionnent pas.
        / Total = legacy euros + V2 euros; hours (TIM) are not added.
        """
        reponse_de_fedow = {
            "recharges_par_asset": [
                {
                    "uuid": "a",
                    "nom": "FED",
                    "categorie": "FED",
                    "devise": "EUR",
                    "total": 10000,
                    "nombre": 3,
                },
                {
                    "uuid": "b",
                    "nom": "Locale",
                    "categorie": "TLF",
                    "devise": "EUR",
                    "total": 5000,
                    "nombre": 2,
                },
                {
                    "uuid": "c",
                    "nom": "Temps",
                    "categorie": "TIM",
                    "devise": "TMP",
                    "total": 300,
                    "nombre": 1,
                },
            ],
            "cartes": {"total": 9000, "liees_a_un_compte": 6000},
        }
        recharges_v2 = [
            {
                "uuid": "d",
                "nom": "V2",
                "categorie": "TLF",
                "devise": "EUR",
                "total": 700,
                "nombre": 1,
            }
        ]
        totaux_des_lieux = {
            "billets_valides": 4,
            "billets_scannes": 1,
            "minutes_de_benevolat": 90,
        }

        with mock.patch.object(
            observatoire, "statistiques_de_fedow_legacy", return_value=reponse_de_fedow
        ):
            with mock.patch.object(
                observatoire, "recharges_du_moteur_v2", return_value=recharges_v2
            ):
                reseau = observatoire.reseau_depuis_le_debut(5, totaux_des_lieux)

        assert reseau["total_des_recharges_en_centimes"] == 15700
        assert reseau["cartes"] == {"total": 9000, "liees_a_un_compte": 6000}
        assert reseau["fedow_legacy_a_repondu"] is True
        assert reseau["heures_de_benevolat"] == 2

    def test_si_fedow_ne_repond_pas_le_reste_est_calcule(self):
        """
        Fedow injoignable : l'appel rend None, le bloc le dit, le reste est la.
        / Fedow unreachable: None, the block says so, the rest is there.
        """
        with mock.patch.object(
            observatoire.requests,
            "get",
            side_effect=ConnectionError("Fedow éteint"),
        ):
            reseau = observatoire.reseau_depuis_le_debut(
                3,
                {"billets_valides": 0, "billets_scannes": 0, "minutes_de_benevolat": 0},
            )

        assert reseau["fedow_legacy_a_repondu"] is False
        assert reseau["cartes"] is None
        assert reseau["lieux"] == 3
