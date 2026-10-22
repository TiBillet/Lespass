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
from laboutik.models import (
    ArticleCommandeSauvegarde,
    CommandeSauvegarde,
    PointDeVente,
    Table,
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

    def _payer_en_especes(self, articles, somme_donnee_en_centimes):
        """POST payer() en especes, avec la table. / POST payer() in cash, with the table."""
        donnees = self._formulaire_d_addition(articles)
        donnees["moyen_paiement"] = "espece"
        # Panier vide : le vrai #addition-form poste un total VIDE (addition.js ne
        # le remplit qu'au premier article). Le serveur ne le lit jamais.
        # / Empty cart: the real form posts an EMPTY total. The server never reads it.
        donnees["total"] = ""
        donnees["given_sum"] = str(somme_donnee_en_centimes)
        return self.client_http.post("/laboutik/paiement/payer/", data=donnees)

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
        Table choisie : ecran restaurant (zones du bas), pas de grille, bandeau de
        la table et bouton « Ajouter a la table ».
        / Chosen table: restaurant screen, no grid, banner and add-to-table button.
        """
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        reponse = self._ecran_de_la_table()
        html = reponse.content.decode()

        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "laboutik/views/restaurant_interface.html")
        self.assertIn('id="win-bottom-left"', html)
        self.assertIn('id="win-bottom-right"', html)
        self.assertNotIn('data-testid="resto-tables-screen"', html)
        self.assertIn('data-testid="resto-addition-table"', html)
        self.assertIn('data-testid="resto-addition-table-envoye"', html)
        self.assertIn('data-addition-total="1400"', html)
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

    def test_les_touches_suivent_les_moyens_acceptes(self):
        """
        PV « especes seules », carte sans mode gerant : Especes et Cashless, pas de
        CB, Cheque, Mixte ni Offrir. Ticket de caisse, voyants, VALIDER et
        « Poser carte » ont disparu ; « Check carte » est la.
        / Cash-only POS: only cash and cashless keys; removed keys are gone.
        """
        self.point_de_vente.accepte_carte_bancaire = False
        self.point_de_vente.accepte_cheque = False
        self.point_de_vente.save()

        html = self._ecran_de_la_table().content.decode()

        self.assertIn('data-testid="resto-touche-especes"', html)
        self.assertIn('data-testid="resto-touche-cashless"', html)
        for touche_absente in [
            "resto-touche-cb",
            "resto-touche-cheque",
            "resto-touche-mixte",
            "resto-touche-offrir",
            "resto-touche-ticket",
            "resto-touche-valider",
            "resto-statuts",
            "resto-action-poser-carte",
        ]:
            self.assertNotIn(f'data-testid="{touche_absente}"', html, touche_absente)
        self.assertIn('data-testid="resto-action-check-carte"', html)

    def test_la_touche_mixte_apparait_avec_deux_moyens(self):
        """Especes + CB : la touche Mixte est la. / Cash + card: the Mixed key shows."""
        self.point_de_vente.accepte_cheque = False
        self.point_de_vente.save()

        html = self._ecran_de_la_table().content.decode()

        self.assertIn('data-testid="resto-touche-mixte"', html)
        self.assertIn('data-testid="resto-touche-cb"', html)
        self.assertNotIn('data-testid="resto-touche-cheque"', html)

    def test_les_touches_de_paiement_suivent_l_ordre_des_tuiles(self):
        """
        Meme ordre que _tuiles_paiement.html : Carte TiBillet, Especes, CB, Cheque,
        Mixte (Offrir seulement en mode gerant).
        / Same order as the payment tiles.
        """
        html = self._ecran_de_la_table().content.decode()

        ordre_attendu = [
            "resto-touche-cashless",
            "resto-touche-especes",
            "resto-touche-cb",
            "resto-touche-cheque",
            "resto-touche-mixte",
        ]
        positions = []
        for data_testid in ordre_attendu:
            positions.append(html.index(f'data-testid="{data_testid}"'))
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Carte TiBillet", html)

    def test_le_ticket_n_a_plus_de_boutons_en_mode_restaurant(self):
        """
        Mode restaurant : Vider, « Ajouter a la table » et « Envoi prepa » sont des
        touches de la zone bas-droite. Le ticket garde son total, sans boutons.
        / Restaurant mode: the ticket keeps its total, no buttons.
        """
        html = self._ecran_de_la_table().content.decode()

        self.assertNotIn('class="addition-actions"', html)
        self.assertNotIn('data-testid="addition-check-carte"', html)
        self.assertIn('data-testid="addition-total-affiche"', html)
        zone_du_bas = html[html.index('id="win-bottom-right"') :]
        self.assertIn('data-testid="addition-vider"', zone_du_bas)
        self.assertIn('data-testid="addition-ajouter-a-la-table"', zone_du_bas)
        self.assertIn('data-testid="resto-touche-envoyer-prepa"', zone_du_bas)

    def test_sans_table_ni_ajout_ni_envoi_prepa(self):
        """
        « Continuer sans table » : la touche Vider reste, pas d'« Ajouter a la
        table » ni d'« Envoi prepa ».
        / Without a table: Empty stays, no add-to-table nor send-to-prep.
        """
        html = self.client_http.get(
            "/laboutik/caisse/point_de_vente/",
            {"uuid_pv": str(self.point_de_vente.uuid)},
        ).content.decode()

        self.assertIn('data-testid="addition-vider"', html)
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
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        self._ajouter_a_la_table([(self.cafe, self.prix_du_cafe, 1)])

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
        self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])
        with mock.patch("laboutik.views.imprimer_commande"):
            self._envoyer_en_preparation([])

        with mock.patch("laboutik.views.imprimer_commande") as tache_d_impression:
            with self.captureOnCommitCallbacks(execute=True):
                reponse = self._envoyer_en_preparation([])

        self.assertEqual(reponse.status_code, 400)
        tache_d_impression.delay.assert_not_called()

    def test_l_ajout_a_la_table_attend_l_envoi_prepa(self):
        """
        « Ajouter a la table » ne part pas en cuisine : l'article reste EN_ATTENTE
        et le bandeau affiche « 1 a envoyer ».
        / Add to table does not reach the kitchen: the banner shows "1 to send".
        """
        reponse = self._ajouter_a_la_table([(self.burger, self.prix_du_burger, 1)])

        article = ArticleCommandeSauvegarde.objects.get(commande__table=self.table)
        self.assertEqual(article.statut, ArticleCommandeSauvegarde.EN_ATTENTE)
        self.assertIn(
            'data-testid="resto-addition-table-a-envoyer"', reponse.content.decode()
        )
