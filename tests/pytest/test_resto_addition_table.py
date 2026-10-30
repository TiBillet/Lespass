"""
tests/pytest/test_resto_addition_table.py — Addition d'une table du mode restaurant.
/ Restaurant mode table bill.

LOCALISATION : tests/pytest/test_resto_addition_table.py

CE QUI EST COUVERT / WHAT IS COVERED :
- « Ajouter a la table » (CommandeViewSet.ajouter_a_la_table) : une Vente EN_ATTENTE
  par table, une commande par envoi, table OCCUPEE. Rien n'est ecrit pour un article
  refuse (retour de consigne).
- Paiement d'une table (payer avec id_table) : l'addition + le panier en cours sont
  encaisses dans la vente de l'addition. Commandes PAID, table LIBRE.
- payer_commande refuse une commande qui fait partie d'une addition.
- Ecran d'une table choisie : ecran restaurant, bandeau, bouton « Ajouter a la table ».
- Touches du bas : seulement les moyens acceptes par le point de vente, dans
  l'ordre des tuiles de paiement. Vider, « Ajouter a la table » et « Envoi prepa »
  sont des touches ; le ticket n'a plus de boutons en mode restaurant.
- « Envoi prepa » (CommandeViewSet.envoyer_en_preparation) : articles EN_COURS,
  un ticket par commande envoyee, rien de plus au 2e appui.
- Stock : les tables comptent comme reservees, une addition reste encaissable.
- Encaissement bloque si des articles a preparer ne sont pas envoyes. Les articles
  d'une categorie sans imprimante ne bloquent pas.
- Prix fige a la commande, total annonce compare au total recalcule.
- Table a 0 €, suppression d'une table, reimpression, concurrence, alerte d'impression.

Lancement / Run:
    poetry run pytest tests/pytest/test_resto_addition_table.py -v
"""

import sys

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

from decimal import Decimal
from unittest import mock

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    CategorieProduct,
    Configuration,
    LigneArticle,
    Price,
    Product,
)
from BaseBillet.models_vente import Vente
from inventaire.models import Stock
from laboutik.models import (
    ArticleCommandeSauvegarde,
    CommandeSauvegarde,
    PointDeVente,
    Printer,
    Table,
)
from laboutik.printing.tasks import imprimer_commande
from laboutik.services_table import (
    AdditionDejaReglee,
    AdditionModifiee,
    ajouter_le_panier_a_la_table,
    articles_panier_de_l_addition,
    cloturer_l_addition,
    reprendre_la_vente_de_l_addition,
    resume_de_l_addition,
)


class TestRestoAdditionTable(FastTenantTestCase):
    """
    L'addition d'une table : envois, paiement, ecran.
    / A table bill: sends, payment, screen.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_resto_addition_table"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-resto-addition-table.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = "Test Resto Addition Table"

    def setUp(self):
        """Un burger a 14 €, un cafe a 2 €, une salle sans service direct, Table 4.
        / A 14 € burger, a 2 € coffee, a table-service room, Table 4."""
        connection.set_tenant(self.tenant)

        configuration = Configuration.get_solo()
        configuration.module_caisse = True
        configuration.save()

        self.categorie = CategorieProduct.objects.create(name="Carte test addition")
        self.burger = Product.objects.create(
            name="Burger test addition",
            categorie_article=Product.VENTE,
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
            publish=True,
        )
        self.prix_du_burger = Price.objects.create(
            product=self.burger, name="Assiette", prix=Decimal("14.00"), publish=True
        )
        self.cafe = Product.objects.create(
            name="Cafe test addition",
            categorie_article=Product.VENTE,
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
            publish=True,
        )
        self.prix_du_cafe = Price.objects.create(
            product=self.cafe, name="Tasse", prix=Decimal("2.00"), publish=True
        )
        self.consigne = Product.objects.create(
            name="Retour gobelet test addition",
            methode_caisse=Product.RETOUR_CONSIGNE,
            categorie_pos=self.categorie,
            publish=True,
        )
        self.prix_de_la_consigne = Price.objects.create(
            product=self.consigne, name="Gobelet", prix=Decimal("-1.00"), publish=True
        )

        self.point_de_vente = PointDeVente.objects.create(
            name="Salle test addition",
            comportement=PointDeVente.DIRECT,
            service_direct=False,
            accepte_commandes=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            accepte_cheque=True,
        )
        self.point_de_vente.products.add(self.burger, self.cafe, self.consigne)

        self.table = Table.objects.create(name="Table 4 test addition")

        self.caissier, _cree = TibilletUser.objects.get_or_create(
            email="caissier-resto-addition@tibillet.localhost",
            defaults={
                "username": "caissier-resto-addition@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.caissier.client_admin.add(self.tenant)
        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.caissier)

    # ------------------------------------------------------------------ #
    #  Outils / Helpers
    # ------------------------------------------------------------------ #

    def _formulaire_d_addition(self, articles):
        """Les champs de #addition-form. articles = [(produit, prix, quantite)].
        / The #addition-form fields."""
        donnees = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "id_table": str(self.table.uuid),
            "tag_id_cm": "",
            "type_app": "unknown",
        }
        for produit, prix, quantite in articles:
            donnees[f"repid-{produit.uuid}--{prix.uuid}"] = str(quantite)
        return donnees

    def _ajouter_a_la_table(self, articles):
        """POST du bouton « Ajouter a la table ». / POST of the add-to-table button."""
        return self.client_http.post(
            "/laboutik/commande/ajouter_a_la_table/",
            data=self._formulaire_d_addition(articles),
        )

    def _brancher_la_cuisine(self):
        """La categorie du burger et du cafe imprime en cuisine.
        / The burger and coffee category prints in the kitchen."""
        self.imprimante = Printer.objects.create(
            name="Cuisine test addition", printer_type=Printer.MOCK, active=True
        )
        self.categorie.printer = self.imprimante
        self.categorie.save()

    def _creer_une_boisson(self):
        """Une biere a 5 €, dans une categorie sans imprimante.
        / A 5 € beer, in a category without a printer."""
        categorie_du_bar = CategorieProduct.objects.create(name="Bar test addition")
        biere = Product.objects.create(
            name="Biere test addition",
            categorie_article=Product.VENTE,
            methode_caisse=Product.VENTE,
            categorie_pos=categorie_du_bar,
            publish=True,
        )
        prix_de_la_biere = Price.objects.create(
            product=biere, name="Pinte", prix=Decimal("5.00"), publish=True
        )
        self.point_de_vente.products.add(biere)
        return biere, prix_de_la_biere

    def _total_annonce(self):
        """Le total pose par moyens_paiement dans le formulaire.
        / The total put in the form by moyens_paiement."""
        return str(resume_de_l_addition(self.table)["total_centimes"])

    def _poser_sans_envoyer(self, articles):
        """Une commande pas encore envoyee, sans passer par le bouton (qui envoie).
        / An order not sent yet, without the button (which sends)."""
        articles_du_panier = []
        for produit, prix, quantite in articles:
            articles_du_panier.append(
                {
                    "product": produit,
                    "price": prix,
                    "quantite": quantite,
                    "prix_centimes": int(prix.prix * 100),
                }
            )
        ajouter_le_panier_a_la_table(
            self.table, self.point_de_vente, articles_du_panier, None
        )

    def _payer_en_especes(self, articles, somme_donnee_en_centimes):
        """POST payer() en especes, avec la table. / POST payer() in cash, with the table."""
        donnees = self._formulaire_d_addition(articles)
        donnees["moyen_paiement"] = "espece"
        donnees["total_attendu_addition"] = self._total_de_la_table_et_du_panier(articles)
        # Panier vide : le vrai #addition-form poste un total VIDE (addition.js ne
        # le remplit qu'au premier article). Le serveur ne le lit jamais.
        # / Empty cart: the real form posts an EMPTY total. The server never reads it.
        donnees["total"] = ""
        donnees["given_sum"] = str(somme_donnee_en_centimes)
        return self.client_http.post("/laboutik/paiement/payer/", data=donnees)

    def _total_de_la_table_et_du_panier(self, articles):
        """Le total annonce au caissier : addition + panier.
        / The total shown to the cashier: bill + cart."""
        total_du_panier = 0
        for _produit, prix, quantite in articles:
            total_du_panier += int(prix.prix * 100) * quantite
        return str(int(self._total_annonce()) + total_du_panier)

    def _ecran_de_la_table(self):
        """GET de l'ecran de la table choisie. / GET of the chosen table screen."""
        return self.client_http.get(
            "/laboutik/caisse/point_de_vente/",
            {
                "uuid_pv": str(self.point_de_vente.uuid),
                "id_table": str(self.table.uuid),
            },
        )

    # ------------------------------------------------------------------ #
    #  Ajouter a la table / Add to table
    # ------------------------------------------------------------------ #

    def test_le_premier_envoi_ouvre_une_vente_en_attente(self):
        """
        1er envoi : une Vente EN_ATTENTE sans article, une commande OPEN qui la
        porte, la table passe Occupee. La reponse met a jour le bandeau.
        / First send: a pending sale, an open order carrying it, table occupied.
        """
        reponse = self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 2)])

        self.assertEqual(reponse.status_code, 200)
        commande = CommandeSauvegarde.objects.get(table=self.table)
        self.assertEqual(commande.statut, CommandeSauvegarde.OPEN)
        self.assertEqual(commande.vente.statut, Vente.Statut.EN_ATTENTE)
        self.assertIsNone(commande.vente.numero)
        self.assertEqual(LigneArticle.objects.filter(vente=commande.vente).count(), 0)
        self.assertEqual(commande.articles.get().qty, 2)
        self.table.refresh_from_db()
        self.assertEqual(self.table.statut, Table.OCCUPEE)

        html = reponse.content.decode()
        self.assertIn('id="addition-table"', html)
        self.assertIn('hx-swap-oob="true"', html)
        self.assertIn("28,00", html)

    def test_un_deuxieme_envoi_garde_la_meme_vente(self):
        """
        2e envoi : une 2e commande, rattachee a la MEME vente.
        / Second send: a second order on the SAME sale.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        self._ajouter_a_la_table([(self.cafe, self.prix_du_cafe, 2)])

        commandes = CommandeSauvegarde.objects.filter(table=self.table)
        self.assertEqual(commandes.count(), 2)
        self.assertEqual(len({commande.vente_id for commande in commandes}), 1)
        self.assertEqual(
            Vente.objects.filter(statut=Vente.Statut.EN_ATTENTE).count(), 1
        )

    def test_un_retour_de_consigne_est_refuse_sans_rien_ecrire(self):
        """
        Un article qui se regle au comptoir bloque tout l'envoi : 400, rien en base.
        / A counter-only article blocks the whole send: 400, nothing written.
        """
        reponse = self._ajouter_a_la_table(
            [
                (self.burger, self.prix_du_burger, 1),
                (self.consigne, self.prix_de_la_consigne, 1),
            ]
        )

        self.assertEqual(reponse.status_code, 400)
        self.assertFalse(CommandeSauvegarde.objects.exists())
        self.assertFalse(Vente.objects.exists())
        self.table.refresh_from_db()
        self.assertEqual(self.table.statut, Table.LIBRE)

    def test_un_panier_vide_est_refuse(self):
        """Panier vide : 400, rien en base. / Empty cart: 400, nothing written."""
        reponse = self._ajouter_a_la_table([])

        self.assertEqual(reponse.status_code, 400)
        self.assertFalse(CommandeSauvegarde.objects.exists())

    # ------------------------------------------------------------------ #
    #  Paiement de la table / Paying the table
    # ------------------------------------------------------------------ #

    def test_payer_la_table_encaisse_la_vente_de_l_addition(self):
        """
        Panier vide + table qui doit 28 € : les especes encaissent l'addition dans
        SA vente. Vente REGLEE numerotee, commande PAID, table Libre.
        / Empty cart + table owing 28 €: cash settles the bill's own sale.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 2)])
        vente_de_l_addition = CommandeSauvegarde.objects.get(table=self.table).vente

        reponse = self._payer_en_especes([], somme_donnee_en_centimes=2800)

        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:500])
        vente_de_l_addition.refresh_from_db()
        self.assertEqual(vente_de_l_addition.statut, Vente.Statut.REGLEE)
        self.assertIsNotNone(vente_de_l_addition.numero)
        self.assertEqual(vente_de_l_addition.total_ttc, 2800)
        self.assertEqual(Vente.objects.count(), 1)
        commande = CommandeSauvegarde.objects.get(table=self.table)
        self.assertEqual(commande.statut, CommandeSauvegarde.PAID)
        self.table.refresh_from_db()
        self.assertEqual(self.table.statut, Table.LIBRE)
        # OK de l'ecran de succes : retour a la grille des tables (sans id_table).
        # / Success OK: back to the table grid.
        html = reponse.content.decode()
        self.assertIn(
            f"window.location = '/laboutik/caisse/point_de_vente/?uuid_pv={self.point_de_vente.uuid}",
            html,
        )

    def test_payer_la_table_encaisse_aussi_le_panier_en_cours(self):
        """
        Addition de 14 € + panier de 4 € : 18 € encaisses dans la vente de
        l'addition. Le panier devient une derniere commande, payee elle aussi.
        / 14 € bill + 4 € cart: 18 € in the bill's sale; the cart becomes a paid order.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        vente_de_l_addition = CommandeSauvegarde.objects.get(table=self.table).vente

        reponse = self._payer_en_especes(
            [(self.cafe, self.prix_du_cafe, 2)], somme_donnee_en_centimes=1800
        )

        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:500])
        vente_de_l_addition.refresh_from_db()
        self.assertEqual(vente_de_l_addition.statut, Vente.Statut.REGLEE)
        self.assertEqual(vente_de_l_addition.total_ttc, 1800)
        commandes = CommandeSauvegarde.objects.filter(table=self.table)
        self.assertEqual(commandes.count(), 2)
        for commande in commandes:
            self.assertEqual(commande.statut, CommandeSauvegarde.PAID)
            self.assertEqual(commande.vente_id, vente_de_l_addition.pk)

    def test_les_moyens_de_paiement_affichent_le_total_de_l_addition(self):
        """
        Avec la table, moyens_paiement calcule sur addition + panier (14 + 2 €).
        / With the table, moyens_paiement totals bill + cart.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        donnees = self._formulaire_d_addition([(self.cafe, self.prix_du_cafe, 1)])
        reponse = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/", data=donnees
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context["total"], 16.0)

    def test_payer_commande_refuse_une_commande_d_addition(self):
        """
        Une commande de l'addition ne se paie pas seule : 400, vente intacte.
        / An order of the bill is not paid alone: 400, sale untouched.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        commande = CommandeSauvegarde.objects.get(table=self.table)

        reponse = self.client_http.post(
            f"/laboutik/commande/payer/{commande.uuid}/",
            data={"uuid_pv": str(self.point_de_vente.uuid), "moyen_paiement": "espece"},
        )

        self.assertEqual(reponse.status_code, 400)
        commande.vente.refresh_from_db()
        self.assertEqual(commande.vente.statut, Vente.Statut.EN_ATTENTE)

    # ------------------------------------------------------------------ #
    #  Ecran de la table / Table screen
    # ------------------------------------------------------------------ #

    def test_l_ecran_de_la_table_garde_l_ecran_restaurant(self):
        """
        Table choisie : ecran restaurant, categories a gauche dans main comme le
        service direct, sans zones du bas ni grille. Bandeau de la table et bouton
        « Ajouter a la table ».
        / Chosen table: restaurant screen, no grid, banner and add-to-table button.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        reponse = self._ecran_de_la_table()
        html = reponse.content.decode()

        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "laboutik/views/restaurant_interface.html")
        self.assertIn('data-testid="caisse-pv-interface"', html)
        self.assertIn('id="categories"', html)
        self.assertNotIn('id="win-bottom-left"', html)
        self.assertNotIn('id="win-bottom-right"', html)
        self.assertNotIn('data-testid="resto-tables-screen"', html)
        self.assertIn('data-testid="resto-addition-table"', html)
        self.assertIn('data-testid="resto-addition-table-envoye"', html)
        self.assertIn('data-addition-articles="1"', html)
        self.assertIn('data-testid="addition-ajouter-a-la-table"', html)
        self.assertNotIn('data-testid="addition-valider"', html)

    def test_une_table_inconnue_ramene_a_la_grille(self):
        """
        id_table inconnu : la grille des tables s'affiche, pas de bandeau.
        / Unknown id_table: the table grid shows, no banner.
        """
        reponse = self.client_http.get(
            "/laboutik/caisse/point_de_vente/",
            {
                "uuid_pv": str(self.point_de_vente.uuid),
                "id_table": "00000000-0000-0000-0000-000000000000",
            },
        )
        html = reponse.content.decode()

        self.assertEqual(reponse.status_code, 200)
        self.assertIn('data-testid="resto-tables-screen"', html)
        self.assertNotIn('data-testid="resto-addition-table"', html)

    def test_les_touches_du_bas_sont_cachees(self):
        """
        Touches de paiement, Check carte, CB / Especes et Table : cachees.
        / Payment keys, card check, currency swap and Table keys are hidden.
        """
        html = self._ecran_de_la_table().content.decode()

        for touche_cachee in [
            "resto-touche-cashless",
            "resto-touche-especes",
            "resto-touche-cb",
            "resto-touche-cheque",
            "resto-touche-mixte",
            "resto-touche-offrir",
            "resto-action-check-carte",
            "resto-action-echange",
            "resto-action-table",
        ]:
            self.assertNotIn(f'data-testid="{touche_cachee}"', html, touche_cachee)

    def test_les_boutons_de_la_table_sont_dans_le_ticket(self):
        """
        Avec une table, le bas du ticket montre Vider, Check carte et « Ajouter a la
        table ». « Envoi prepa » n'y est plus. Le total reste.
        / With a table, the ticket bottom shows Empty, card check and add to table.
        """
        html = self._ecran_de_la_table().content.decode()

        self.assertIn('data-testid="addition-total-affiche"', html)
        bas_du_ticket = html[html.index('class="addition-actions"') :]
        self.assertIn('data-testid="addition-vider"', bas_du_ticket)
        self.assertNotIn('data-testid="resto-touche-envoyer-prepa"', html)
        self.assertIn('data-testid="addition-ajouter-a-la-table"', bas_du_ticket)
        self.assertIn('data-testid="addition-check-carte"', bas_du_ticket)
        self.assertNotIn('data-testid="addition-valider"', html)

    def test_encaisser_la_table_apparait_quand_la_table_doit_de_l_argent(self):
        """
        Le bouton suit le chemin de VALIDER. Il apparait avec une addition.
        / The button follows the VALIDER path and shows once there is a bill.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        html = self._ecran_de_la_table().content.decode()

        position_testid = html.index('data-testid="resto-addition-table-encaisser"')
        balise = html[html.rfind("<button", 0, position_testid) : position_testid]
        self.assertIn('onclick="displayPaymentTypes()"', balise)
        self.assertIn('id="addition-table-encaisser"', balise)
        self.assertIn('data-testid="resto-addition-table-encaisser-aide"', html)

    def test_encaisser_la_table_absent_sans_addition(self):
        """Table sans addition : pas de bouton. / No bill: no button."""
        html = self._ecran_de_la_table().content.decode()

        self.assertNotIn('data-testid="resto-addition-table-encaisser"', html)

    def test_sans_table_ni_ajout_ni_envoi_prepa(self):
        """
        « Continuer sans table » : Vider et VALIDER du ticket, pas d'« Ajouter a
        la table » ni d'« Envoi prepa ».
        / Without a table: Empty and validate, no add-to-table nor send-to-prep.
        """
        html = self.client_http.get(
            "/laboutik/caisse/point_de_vente/",
            {"uuid_pv": str(self.point_de_vente.uuid)},
        ).content.decode()

        self.assertIn('data-testid="addition-vider"', html)
        self.assertIn('data-testid="addition-valider"', html)
        self.assertNotIn('data-testid="addition-ajouter-a-la-table"', html)
        self.assertNotIn('data-testid="resto-touche-envoyer-prepa"', html)

    # ------------------------------------------------------------------ #
    #  Envoi prepa / Send to preparation
    # ------------------------------------------------------------------ #

    def _envoyer_en_preparation(self, articles):
        """POST de la touche « Envoi prepa ». / POST of the send-to-prep key."""
        return self.client_http.post(
            "/laboutik/commande/envoyer_en_preparation/",
            data=self._formulaire_d_addition(articles),
        )

    def test_l_envoi_prepa_envoie_les_articles_et_imprime(self):
        """
        Les articles ajoutes passent EN_COURS. Apres le commit, un ticket par
        commande envoyee. Le bandeau ne compte plus rien « a envoyer ».
        / Added articles become in progress; one print per sent order after commit.
        """
        self._brancher_la_cuisine()
        self._poser_sans_envoyer([(self.burger, self.prix_du_burger, 1)])
        self._poser_sans_envoyer([(self.cafe, self.prix_du_cafe, 1)])

        with mock.patch("laboutik.views.imprimer_commande") as tache_d_impression:
            with self.captureOnCommitCallbacks(execute=True):
                reponse = self._envoyer_en_preparation([])

        self.assertEqual(reponse.status_code, 200)
        statuts = set(
            ArticleCommandeSauvegarde.objects.filter(
                commande__table=self.table
            ).values_list("statut", flat=True)
        )
        self.assertEqual(statuts, {ArticleCommandeSauvegarde.EN_COURS})
        self.assertEqual(tache_d_impression.delay.call_count, 2)
        self.assertNotIn("resto-addition-table-a-envoyer", reponse.content.decode())

    def test_l_envoi_prepa_ajoute_d_abord_le_panier(self):
        """
        Panier non vide : il devient une commande de la table, puis part en
        preparation. Un seul appui pour commander et envoyer.
        / Non-empty cart: added to the table first, then sent.
        """
        self._brancher_la_cuisine()
        with mock.patch("laboutik.views.imprimer_commande"):
            reponse = self._envoyer_en_preparation(
                [(self.burger, self.prix_du_burger, 2)]
            )

        self.assertEqual(reponse.status_code, 200)
        article = ArticleCommandeSauvegarde.objects.get(commande__table=self.table)
        self.assertEqual(article.qty, 2)
        self.assertEqual(article.statut, ArticleCommandeSauvegarde.EN_COURS)
        self.assertEqual(article.commande.vente.statut, Vente.Statut.EN_ATTENTE)

    def test_un_deuxieme_envoi_prepa_n_envoie_rien(self):
        """
        Tout est deja en preparation : 400, aucune impression.
        / Everything already sent: 400, no print.
        """
        self._brancher_la_cuisine()
        self._poser_sans_envoyer([(self.burger, self.prix_du_burger, 1)])
        with mock.patch("laboutik.views.imprimer_commande"):
            self._envoyer_en_preparation([])

        with mock.patch("laboutik.views.imprimer_commande") as tache_d_impression:
            with self.captureOnCommitCallbacks(execute=True):
                reponse = self._envoyer_en_preparation([])

        self.assertEqual(reponse.status_code, 400)
        tache_d_impression.delay.assert_not_called()

    def test_ajouter_a_la_table_envoie_en_preparation(self):
        """
        « Ajouter a la table » envoie le panier : article EN_COURS, ticket imprime
        apres le commit, rien « a envoyer », panier vide au retour.
        / Add to table sends the cart: in progress, printed after commit.
        """
        self._brancher_la_cuisine()

        with mock.patch("laboutik.views.imprimer_commande") as tache_d_impression:
            with self.captureOnCommitCallbacks(execute=True):
                reponse = self._ajouter_a_la_table(
                    [(self.burger, self.prix_du_burger, 1)]
                )

        self.assertEqual(reponse.status_code, 200)
        article = ArticleCommandeSauvegarde.objects.get(commande__table=self.table)
        self.assertEqual(article.statut, ArticleCommandeSauvegarde.EN_COURS)
        tache_d_impression.delay.assert_called_once_with(
            str(article.commande.uuid), self.tenant.schema_name
        )
        html = reponse.content.decode()
        self.assertIn("manageReset();", html)
        self.assertNotIn('data-testid="resto-addition-table-a-envoyer"', html)

    def test_ajouter_a_la_table_rattrape_les_articles_non_envoyes(self):
        """
        Des articles attendaient : ils partent avec le panier, un ticket par commande.
        / Waiting articles leave with the cart, one ticket per order.
        """
        self._brancher_la_cuisine()
        self._poser_sans_envoyer([(self.cafe, self.prix_du_cafe, 1)])

        with mock.patch("laboutik.views.imprimer_commande") as tache_d_impression:
            with self.captureOnCommitCallbacks(execute=True):
                self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        self.assertEqual(tache_d_impression.delay.call_count, 2)
        self.assertEqual(resume_de_l_addition(self.table)["nombre_a_envoyer"], 0)

    # ------------------------------------------------------------------ #
    #  Articles sans preparation / Articles without preparation
    # ------------------------------------------------------------------ #

    def test_le_badge_ne_compte_que_les_articles_a_preparer(self):
        """
        2 burgers (cuisine) + 3 bieres (sans imprimante) non envoyes : « 2 a envoyer ».
        / 2 burgers + 3 beers not sent: only the burgers count as to send.
        """
        self._brancher_la_cuisine()
        biere, prix_de_la_biere = self._creer_une_boisson()

        self._poser_sans_envoyer(
            [(self.burger, self.prix_du_burger, 2), (biere, prix_de_la_biere, 3)]
        )

        self.assertEqual(resume_de_l_addition(self.table)["nombre_a_envoyer"], 2)
        html = self._ecran_de_la_table().content.decode()
        self.assertIn('data-testid="resto-addition-table-a-envoyer"', html)
        self.assertIn("sans préparation", html)

    def test_des_boissons_seules_n_affichent_aucun_badge(self):
        """
        Que des boissons : pas de badge, et l'encaissement reste possible.
        / Drinks only: no badge, and the table can be paid.
        """
        biere, prix_de_la_biere = self._creer_une_boisson()

        reponse = self._ajouter_a_la_table([(biere, prix_de_la_biere, 2)])

        html = reponse.content.decode()
        self.assertNotIn('data-testid="resto-addition-table-a-envoyer"', html)
        self.assertEqual(self._payer_en_especes([], 1000).status_code, 200)

    def test_l_envoi_prepa_d_un_panier_de_boissons_ajoute_sans_imprimer(self):
        """
        Panier de boissons + « Envoi prepa » : il est ajoute, le succes vide le
        panier, rien ne s'imprime. Un refus laisserait le panier et le doublerait.
        / Drinks cart: added, success empties the cart, nothing prints.
        """
        biere, prix_de_la_biere = self._creer_une_boisson()

        with mock.patch("laboutik.views.imprimer_commande") as tache_d_impression:
            with self.captureOnCommitCallbacks(execute=True):
                reponse = self._envoyer_en_preparation([(biere, prix_de_la_biere, 1)])

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("manageReset();", reponse.content.decode())
        tache_d_impression.delay.assert_not_called()
        article = ArticleCommandeSauvegarde.objects.get(commande__table=self.table)
        self.assertEqual(article.statut, ArticleCommandeSauvegarde.EN_ATTENTE)

    def test_l_envoi_prepa_signale_une_imprimante_desactivee(self):
        """
        Imprimante desactivee : le serveur le voit tout de suite.
        / Disabled printer: the waiter is told right away.
        """
        self._brancher_la_cuisine()
        self.imprimante.active = False
        self.imprimante.save()
        self._poser_sans_envoyer([(self.burger, self.prix_du_burger, 1)])

        with mock.patch("laboutik.views.imprimer_commande"):
            reponse = self._envoyer_en_preparation([])

        self.assertIn("Cuisine test addition", reponse.content.decode())

    # ------------------------------------------------------------------ #
    #  Encaissement bloque / Blocked payment
    # ------------------------------------------------------------------ #

    def test_une_table_avec_un_plat_non_envoye_n_est_pas_encaissee(self):
        """
        Un plat non envoye bloque le paiement : rien n'est regle.
        / An unsent dish blocks the payment: nothing is settled.
        """
        self._brancher_la_cuisine()
        self._poser_sans_envoyer([(self.burger, self.prix_du_burger, 1)])

        reponse = self._payer_en_especes([], 1400)

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("avant d", reponse.content.decode())
        self.assertEqual(Vente.objects.get().statut, Vente.Statut.EN_ATTENTE)

    def test_les_moyens_de_paiement_refusent_un_plat_non_envoye(self):
        """Meme refus avant d'afficher les moyens. / Same refusal before the methods."""
        self._brancher_la_cuisine()
        self._poser_sans_envoyer([(self.burger, self.prix_du_burger, 1)])

        reponse = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/",
            data=self._formulaire_d_addition([]),
        )

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("avant d", reponse.content.decode())

    def test_un_panier_a_preparer_paye_avec_la_table_est_refuse(self):
        """
        Addition de boissons + burger au panier : le burger n'irait jamais en
        cuisine. Refus, rien n'est regle.
        / Drinks on the bill + a burger in the cart: refused, nothing settled.
        """
        self._brancher_la_cuisine()
        biere, prix_de_la_biere = self._creer_une_boisson()
        self._ajouter_a_la_table([(biere, prix_de_la_biere, 1)])

        reponse = self._payer_en_especes(
            [(self.burger, self.prix_du_burger, 1)], 1900
        )

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("envoyez-le", reponse.content.decode())
        self.assertEqual(Vente.objects.get().statut, Vente.Statut.EN_ATTENTE)

    def test_un_panier_de_boissons_paye_avec_la_table_est_accepte(self):
        """Rien a preparer : le panier est encaisse. / Nothing to prepare: paid."""
        self._brancher_la_cuisine()
        biere, prix_de_la_biere = self._creer_une_boisson()
        self._ajouter_a_la_table([(biere, prix_de_la_biere, 1)])

        reponse = self._payer_en_especes([(biere, prix_de_la_biere, 1)], 1000)

        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:500])

    def test_le_bouton_encaisser_est_grise_si_un_plat_reste_a_envoyer(self):
        """Le serveur rend le bouton grise. / The server renders it disabled."""
        self._brancher_la_cuisine()
        self._poser_sans_envoyer([(self.burger, self.prix_du_burger, 1)])

        html = self._ecran_de_la_table().content.decode()

        self.assertIn('data-a-envoyer="1"', html)
        self.assertIn("ajoutez un article à la table", html)

    # ------------------------------------------------------------------ #
    #  Stock / Stock
    # ------------------------------------------------------------------ #

    def test_une_deuxieme_table_ne_depasse_pas_le_stock(self):
        """
        Stock de 2, table A commande 2 : table B est refusee, sans rien ecrire.
        / Stock of 2, table A orders 2: table B is refused, nothing written.
        """
        Stock.objects.create(
            product=self.burger, quantite=2, autoriser_vente_hors_stock=False
        )
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 2)])
        self.table = Table.objects.create(name="Table 5 test addition")

        reponse = self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("0 en stock", reponse.content.decode())
        self.assertFalse(CommandeSauvegarde.objects.filter(table=self.table).exists())

    def test_la_vente_directe_compte_les_tables_en_attente(self):
        """
        Stock 4, 3 reserves en table : direct 2 refuse, direct 1 accepte, puis la
        table reste encaissable, sans bloquer.
        / Stock 4, 3 reserved: direct 2 refused, direct 1 ok, the table can be paid.
        """
        stock = Stock.objects.create(
            product=self.burger, quantite=4, autoriser_vente_hors_stock=False
        )
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 3)])

        def _vente_directe(quantite):
            donnees = self._formulaire_d_addition(
                [(self.burger, self.prix_du_burger, quantite)]
            )
            donnees["id_table"] = ""
            donnees["moyen_paiement"] = "espece"
            donnees["given_sum"] = str(1400 * quantite)
            return self.client_http.post("/laboutik/paiement/payer/", data=donnees)

        refus = _vente_directe(2)
        self.assertEqual(refus.status_code, 400)
        self.assertIn("1 en stock", refus.content.decode())

        self.assertEqual(_vente_directe(1).status_code, 200)

        self.assertEqual(self._payer_en_especes([], 4200).status_code, 200)
        stock.refresh_from_db()
        self.assertEqual(stock.quantite, 0)
        self.table.refresh_from_db()
        self.assertEqual(self.table.statut, Table.LIBRE)

    def test_une_addition_reste_encaissable_si_le_stock_a_disparu(self):
        """
        Le stock tombe a 0 apres la commande : la table se paie quand meme.
        / Stock drops to 0 after the order: the table is still paid.
        """
        stock = Stock.objects.create(
            product=self.burger, quantite=1, autoriser_vente_hors_stock=False
        )
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        stock.quantite = 0
        stock.save()

        self.assertEqual(self._payer_en_especes([], 1400).status_code, 200)

    # ------------------------------------------------------------------ #
    #  Montant / Amount
    # ------------------------------------------------------------------ #

    def test_le_prix_est_fige_a_la_commande(self):
        """
        Le tarif passe a 20 € apres la commande : la table paie 14 €.
        / The price rises after the order: the table pays the order price.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        self.prix_du_burger.prix = Decimal("20.00")
        self.prix_du_burger.save()

        reponse = self._payer_en_especes([], 1400)

        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:500])
        self.assertEqual(Vente.objects.get().total_ttc, 1400)

    def test_deux_prix_du_meme_tarif_donnent_deux_lignes(self):
        """
        Meme tarif commande avant et apres un changement : deux prix, deux lignes.
        / Same price ordered before and after a change: two lines.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        self.prix_du_burger.prix = Decimal("20.00")
        self.prix_du_burger.save()
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        self.assertEqual(len(articles_panier_de_l_addition(self.table)), 2)
        self.assertEqual(resume_de_l_addition(self.table)["total_centimes"], 3400)

    def test_un_total_change_pendant_le_paiement_est_refuse(self):
        """
        L'ecran annonce 14 €, un autre terminal ajoute 14 € : le paiement est
        refuse, rien n'est regle.
        / Screen shows 14, another terminal adds 14: refused, nothing settled.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        total_annonce = self._total_annonce()
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        donnees = self._formulaire_d_addition([])
        donnees["moyen_paiement"] = "carte_bancaire"
        donnees["total_attendu_addition"] = total_annonce
        reponse = self.client_http.post("/laboutik/paiement/payer/", data=donnees)

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("14.00", reponse.content.decode())
        self.assertIn("28.00", reponse.content.decode())
        self.assertEqual(Vente.objects.get().statut, Vente.Statut.EN_ATTENTE)

    def test_un_paiement_sans_total_annonce_est_refuse(self):
        """Avec une addition, le champ est obligatoire. / The field is required."""
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        donnees = self._formulaire_d_addition([])
        donnees["moyen_paiement"] = "carte_bancaire"
        reponse = self.client_http.post("/laboutik/paiement/payer/", data=donnees)

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("encaissez le nouveau total", reponse.content.decode())

    def test_les_moyens_de_paiement_posent_le_total_annonce(self):
        """Le champ hors bande porte le total. / The out-of-band field holds the total."""
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        html = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/",
            data=self._formulaire_d_addition([]),
        ).content.decode()

        self.assertRegex(html, r'name="total_attendu_addition"\s+value="1400"')

    # ------------------------------------------------------------------ #
    #  Table a 0 €, suppression / Zero bill, deletion
    # ------------------------------------------------------------------ #

    def _ajouter_un_article_gratuit(self):
        """Un cafe offert, a 0 €. / A free coffee, at 0 €."""
        prix_offert = Price.objects.create(
            product=self.cafe, name="Offert", prix=Decimal("0.00"), publish=True
        )
        self._ajouter_a_la_table([(self.cafe, prix_offert, 1)])

    def test_une_table_a_zero_euro_s_encaisse(self):
        """
        Addition a 0 € : le bouton est la, VALIDER gratuit aussi, la table se libere.
        / Zero bill: the button shows, free VALIDER too, the table is freed.
        """
        self._ajouter_un_article_gratuit()

        self.assertIn(
            'id="addition-table-encaisser"', self._ecran_de_la_table().content.decode()
        )
        moyens = self.client_http.post(
            "/laboutik/paiement/moyens_paiement/",
            data=self._formulaire_d_addition([]),
        ).content.decode()
        self.assertIn('data-testid="paiement-btn-gratuit"', moyens)

        donnees = self._formulaire_d_addition([])
        donnees["moyen_paiement"] = "gift"
        donnees["total_attendu_addition"] = "0"
        reponse = self.client_http.post("/laboutik/paiement/payer/", data=donnees)

        self.assertEqual(reponse.status_code, 200, reponse.content.decode()[:500])
        self.table.refresh_from_db()
        self.assertEqual(self.table.statut, Table.LIBRE)

    def _supprimer_la_table(self):
        return self.client_http.post(
            "/laboutik/commande/supprimer_table/",
            data=self._formulaire_d_addition([]),
        )

    def test_supprimer_une_table_vide_l_archive(self):
        """
        Table vide : archivee, retour a la grille, absente de la grille.
        / Empty table: archived, back to the grid, not in the grid.
        """
        reponse = self._supprimer_la_table()

        self.assertEqual(reponse.status_code, 204)
        self.assertIn("uuid_pv", reponse["HX-Redirect"])
        self.table.refresh_from_db()
        self.assertTrue(self.table.archive)
        grille = self.client_http.get(
            "/laboutik/caisse/point_de_vente/",
            {"uuid_pv": str(self.point_de_vente.uuid)},
        )
        self.assertNotIn(self.table.name, grille.content.decode())

    def test_supprimer_une_table_a_zero_euro_annule_son_addition(self):
        """
        Articles a 0 € : commandes annulees, vente ANNULEE sans numero.
        / Zero-priced articles: orders cancelled, sale cancelled without a number.
        """
        self._ajouter_un_article_gratuit()
        vente = Vente.objects.get()

        self.assertEqual(self._supprimer_la_table().status_code, 204)

        vente.refresh_from_db()
        self.assertEqual(vente.statut, Vente.Statut.ANNULEE)
        self.assertIsNone(vente.numero)
        commande = CommandeSauvegarde.objects.get(table=self.table)
        self.assertEqual(commande.statut, CommandeSauvegarde.CANCEL)
        self.assertEqual(
            commande.articles.get().statut, ArticleCommandeSauvegarde.ANNULE
        )

    def test_supprimer_une_table_qui_doit_de_l_argent_est_refuse(self):
        """Il faut l'encaisser d'abord. / It must be paid first."""
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        reponse = self._supprimer_la_table()

        self.assertEqual(reponse.status_code, 400)
        self.table.refresh_from_db()
        self.assertFalse(self.table.archive)
        self.assertEqual(Vente.objects.get().statut, Vente.Statut.EN_ATTENTE)

    # ------------------------------------------------------------------ #
    #  Concurrence / Concurrency
    # ------------------------------------------------------------------ #

    def test_la_cloture_epargne_la_commande_d_une_autre_vente(self):
        """
        Une commande arrivee pendant le paiement porte une autre vente : elle reste
        a payer, et la table reste occupee.
        / An order arriving during the payment stays due, the table stays occupied.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        vente_payee = Vente.objects.get()
        Vente.objects.filter(pk=vente_payee.pk).update(statut=Vente.Statut.REGLEE)

        self._ajouter_a_la_table([(self.cafe, self.prix_du_cafe, 1)])
        commande_arrivee_apres = CommandeSauvegarde.objects.exclude(
            vente=vente_payee
        ).get()

        cloturer_l_addition(self.table, vente_payee)

        commande_arrivee_apres.refresh_from_db()
        self.assertEqual(commande_arrivee_apres.statut, CommandeSauvegarde.OPEN)
        self.table.refresh_from_db()
        self.assertEqual(self.table.statut, Table.OCCUPEE)

    def test_un_paiement_simultane_affiche_un_message(self):
        """
        Un autre terminal vient d'encaisser : message clair, pas d'erreur 500.
        / Another terminal has just paid: clear message, no 500.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        with mock.patch(
            "laboutik.views.reprendre_la_vente_de_l_addition",
            side_effect=AdditionDejaReglee("deja reglee"),
        ):
            reponse = self._payer_en_especes([], 1400)

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("vient d", reponse.content.decode())
        self.assertEqual(Vente.objects.get().statut, Vente.Statut.EN_ATTENTE)

    def test_reprendre_une_vente_reglee_leve_addition_deja_reglee(self):
        """La vente relue sous verrou n'est plus en attente. / No longer pending."""
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        vente = Vente.objects.get()
        Vente.objects.filter(pk=vente.pk).update(statut=Vente.Statut.REGLEE)

        with self.assertRaises(AdditionDejaReglee):
            reprendre_la_vente_de_l_addition(
                self.table, vente, 1400, idempotency_key="cle-test"
            )

    def test_reprendre_refuse_un_total_different_du_total_lu(self):
        """
        Une commande arrivee avant le verrou change le total : AdditionModifiee.
        / An order arriving before the lock changes the total: refused.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 2)])
        vente = Vente.objects.get()

        with self.assertRaises(AdditionModifiee):
            reprendre_la_vente_de_l_addition(
                self.table, vente, 1400, idempotency_key="cle-test"
            )

    def test_une_commande_arrivee_avant_le_verrou_fait_refuser_le_paiement(self):
        """
        Le paiement a lu 14 €, le verrou relit 28 € : refus, rien n'est regle, rien
        n'est cloture.
        / The payment read 14, the lock reads 28: refused, nothing settled or closed.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 2)])

        with mock.patch("laboutik.views._total_de_l_addition_lu", return_value=1400):
            reponse = self._payer_en_especes([], 2800)

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("L&#x27;addition a changé", reponse.content.decode())
        self.assertEqual(Vente.objects.get().statut, Vente.Statut.EN_ATTENTE)
        commande = CommandeSauvegarde.objects.get(table=self.table)
        self.assertEqual(commande.statut, CommandeSauvegarde.OPEN)

    # ------------------------------------------------------------------ #
    #  Impression / Printing
    # ------------------------------------------------------------------ #

    def _commande_envoyee(self):
        self._brancher_la_cuisine()
        with mock.patch("laboutik.views.imprimer_commande"):
            self._envoyer_en_preparation([(self.burger, self.prix_du_burger, 1)])
        return CommandeSauvegarde.objects.get(table=self.table)

    def test_reimprimer_relance_les_commandes_en_preparation(self):
        """Le panier n'est pas vide par la reponse. / The cart is not reset."""
        commande = self._commande_envoyee()

        with mock.patch("laboutik.views.imprimer_commande") as tache_d_impression:
            reponse = self.client_http.post(
                "/laboutik/commande/reimprimer/",
                data=self._formulaire_d_addition([]),
            )

        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn("manageReset();", reponse.content.decode())
        tache_d_impression.delay.assert_called_once_with(
            str(commande.uuid), self.tenant.schema_name
        )

    def test_reimprimer_relance_un_article_pret(self):
        """Un article PRET reste reimprimable. / A ready article can be printed again."""
        commande = self._commande_envoyee()
        commande.articles.update(statut=ArticleCommandeSauvegarde.PRET)

        self.assertTrue(resume_de_l_addition(self.table)["articles_en_preparation"])
        with mock.patch("laboutik.views.imprimer_commande") as tache_d_impression:
            reponse = self.client_http.post(
                "/laboutik/commande/reimprimer/",
                data=self._formulaire_d_addition([]),
            )

        self.assertEqual(reponse.status_code, 200)
        tache_d_impression.delay.assert_called_once()

    def test_reimprimer_sans_preparation_ne_fait_rien(self):
        """Rien en preparation : 400. / Nothing in preparation: 400."""
        reponse = self.client_http.post(
            "/laboutik/commande/reimprimer/",
            data=self._formulaire_d_addition([]),
        )

        self.assertEqual(reponse.status_code, 400)

    def test_un_echec_d_impression_relance_seulement_cette_imprimante(self):
        """
        Echec : nouvel essai, limite a l'imprimante en echec.
        / Failure: a new try, limited to the failing printer.
        """
        commande = self._commande_envoyee()

        class Relance(Exception):
            pass

        with (
            mock.patch(
                "laboutik.printing.imprimer",
                return_value={"ok": False, "error": "injoignable"},
            ),
            mock.patch.object(
                imprimer_commande, "retry", side_effect=Relance()
            ) as nouvel_essai,
        ):
            with self.assertRaises(Relance):
                imprimer_commande.run(str(commande.uuid), self.tenant.schema_name)

        arguments_du_nouvel_essai = nouvel_essai.call_args.kwargs["args"]
        self.assertEqual(arguments_du_nouvel_essai[2], [str(self.imprimante.pk)])

    def test_le_dernier_echec_d_impression_alerte_les_caisses(self):
        """
        Essais epuises : alerte WebSocket, avec la table et l'imprimante.
        / Tries exhausted: WebSocket alert, with the table and the printer.
        """
        commande = self._commande_envoyee()

        with (
            mock.patch(
                "laboutik.printing.imprimer",
                return_value={"ok": False, "error": "injoignable"},
            ),
            mock.patch.object(
                imprimer_commande,
                "retry",
                side_effect=imprimer_commande.MaxRetriesExceededError(),
            ),
            mock.patch("wsocket.broadcast.broadcast_html") as alerte,
        ):
            imprimer_commande.run(str(commande.uuid), self.tenant.schema_name)

        arguments = alerte.call_args.kwargs
        self.assertEqual(
            arguments["group_name"], f"laboutik-jauges-{self.tenant.schema_name}"
        )
        self.assertEqual(arguments["context"]["nom_de_la_table"], self.table.name)
        self.assertIn(self.imprimante.name, arguments["context"]["noms_des_imprimantes"])

    def test_une_impression_reussie_n_alerte_pas(self):
        """Tout va bien : ni relance, ni alerte. / All good: no retry, no alert."""
        commande = self._commande_envoyee()

        with (
            mock.patch("laboutik.printing.imprimer", return_value={"ok": True}),
            mock.patch.object(imprimer_commande, "retry") as nouvel_essai,
            mock.patch("wsocket.broadcast.broadcast_html") as alerte,
        ):
            imprimer_commande.run(str(commande.uuid), self.tenant.schema_name)

        nouvel_essai.assert_not_called()
        alerte.assert_not_called()

    # ------------------------------------------------------------------ #
    #  Check carte / Card check
    # ------------------------------------------------------------------ #

    def test_check_carte_est_dans_le_ticket_du_mode_restaurant(self):
        """Le bouton est revenu dans #addition. / The button is back in #addition."""
        html = self._ecran_de_la_table().content.decode()

        self.assertIn('data-testid="addition-check-carte"', html)
