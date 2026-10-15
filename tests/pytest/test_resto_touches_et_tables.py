"""
tests/pytest/test_resto_touches_et_tables.py — Clavier du bas et boutons Tables du mode restaurant.
/ Restaurant mode bottom keypad and Tables buttons.

LOCALISATION : tests/pytest/test_resto_touches_et_tables.py

CE QUI EST COUVERT / WHAT IS COVERED :
- Une touche de paiement du clavier (partial/win_bottom_right.html) poste
  moyen_prefere avec #addition-form. moyens_paiement() le rend au gabarit, et la
  tuile de ce moyen porte hx-trigger « load » : elle se declenche seule.
- Un code inconnu, ou un moyen que le comptoir refuse, ne declenche rien.
- La tuile « Nouvelle table » (POST sur ajouter_table) cree une Table libre
  et la choisit (redirection avec id_table).
- La page restaurant porte les liens « Tables » (en-tete, menu, zone du bas)
  vers le point de vente sans id_table, et le message « aucun article ».

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_resto_touches_et_tables.py -v
"""

import sys

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

from decimal import Decimal

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser
from BaseBillet.models import CategorieProduct, Configuration, Price, Product
from laboutik.models import PointDeVente, Table


class TestRestoTouchesEtTables(FastTenantTestCase):
    """
    Les touches de paiement et les boutons Tables du mode restaurant.
    / Restaurant mode payment keys and Tables buttons.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_resto_touches_tables"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-resto-touches-tables.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """Champ requis sur Client. / Required field on Client."""
        tenant.name = "Test Resto Touches Tables"

    def setUp(self):
        connection.set_tenant(self.tenant)

        configuration = Configuration.get_solo()
        configuration.module_caisse = True
        configuration.save()

        self.categorie = CategorieProduct.objects.create(name="Plats test resto touches")
        self.produit = Product.objects.create(
            name="Plat du jour test resto",
            categorie_article=Product.VENTE,
            methode_caisse=Product.VENTE,
            categorie_pos=self.categorie,
            publish=True,
        )
        self.prix = Price.objects.create(
            product=self.produit,
            name="Assiette",
            prix=Decimal("14.00"),
            publish=True,
        )
        self.point_de_vente = PointDeVente.objects.create(
            name="Salle test resto touches",
            comportement=PointDeVente.DIRECT,
            service_direct=False,
            accepte_commandes=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
            accepte_cheque=True,
        )
        self.point_de_vente.products.add(self.produit)

        self.caissier, _cree = TibilletUser.objects.get_or_create(
            email="caissier-resto-touches@tibillet.localhost",
            defaults={
                "username": "caissier-resto-touches@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        self.caissier.client_admin.add(self.tenant)
        self.client_http = TenantClient(self.tenant)
        self.client_http.force_login(self.caissier)

    def _poster_le_panier(self, moyen_prefere):
        """Poste un article a moyens_paiement, avec le moyen choisi d'avance.
        / Posts one article to moyens_paiement with the picked method."""
        donnees = {
            "uuid_pv": str(self.point_de_vente.uuid),
            "total": str(int(round(self.prix.prix * 100))),
            f"repid-{self.produit.uuid}--{self.prix.uuid}": "1",
        }
        if moyen_prefere is not None:
            donnees["moyen_prefere"] = moyen_prefere
        return self.client_http.post("/laboutik/paiement/moyens_paiement/", data=donnees)

    def _attributs_de_la_tuile(self, html, data_testid):
        """Renvoie la balise ouvrante du bouton qui porte ce data-testid.
        / Returns the opening tag of the button carrying this data-testid."""
        position_testid = html.index(f'data-testid="{data_testid}"')
        debut_de_balise = html.rindex("<button", 0, position_testid)
        fin_de_balise = html.index(">", position_testid)
        return html[debut_de_balise:fin_de_balise]

    # ------------------------------------------------------------------ #
    #  Touches de paiement / Payment keys
    # ------------------------------------------------------------------ #

    def test_la_tuile_du_moyen_choisi_se_declenche_seule(self):
        """
        Touche « Chèque » : seule la tuile CHÈQUE porte le declencheur « load ».
        / "Cheque" key: only the cheque tile carries the "load" trigger.
        """
        reponse = self._poster_le_panier("CH")
        html = reponse.content.decode()

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context["moyen_prefere"], "CH")
        tuile_cheque = self._attributs_de_la_tuile(html, "paiement-btn-cheque")
        tuile_especes = self._attributs_de_la_tuile(html, "paiement-btn-especes")
        self.assertIn('hx-trigger="load, click"', tuile_cheque)
        self.assertIn('hx-trigger="click"', tuile_especes)

    def test_sans_touche_rien_ne_se_declenche(self):
        """
        VALIDER du ticket (pas de moyen_prefere) : aucune tuile ne part seule.
        / Ticket VALIDER (no moyen_prefere): no tile fires by itself.
        """
        reponse = self._poster_le_panier(None)

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context["moyen_prefere"], "")
        self.assertNotIn("load, click", reponse.content.decode())

    def test_un_code_inconnu_est_ignore(self):
        """
        Un code hors liste n'arrive jamais au gabarit.
        / An unknown code never reaches the template.
        """
        reponse = self._poster_le_panier("bitcoin")

        self.assertEqual(reponse.context["moyen_prefere"], "")
        self.assertNotIn("load, click", reponse.content.decode())

    def test_un_moyen_refuse_par_le_comptoir_affiche_la_liste(self):
        """
        Touche « Chèque » sur un comptoir qui refuse le cheque : pas de tuile
        CHÈQUE, donc rien ne se declenche, la liste des moyens s'affiche.
        / Cheque key on a counter refusing cheques: the plain list shows.
        """
        self.point_de_vente.accepte_cheque = False
        self.point_de_vente.save()

        reponse = self._poster_le_panier("CH")
        html = reponse.content.decode()

        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn('data-testid="paiement-btn-cheque"', html)
        self.assertNotIn("load, click", html)
        self.assertIn('data-testid="paiement-btn-especes"', html)

    # ------------------------------------------------------------------ #
    #  Page restaurant / Restaurant page
    # ------------------------------------------------------------------ #

    def test_la_page_restaurant_porte_les_liens_tables(self):
        """
        Les trois boutons Tables menent au point de vente sans id_table
        (la grille des tables). Le message « aucun article » est present.
        / The three Tables buttons lead to the POS without id_table.
        """
        reponse = self.client_http.get(
            "/laboutik/caisse/point_de_vente/",
            {"uuid_pv": str(self.point_de_vente.uuid)},
        )
        html = reponse.content.decode()

        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "laboutik/views/restaurant_interface.html")
        lien_de_la_grille = f"/laboutik/caisse/point_de_vente/?uuid_pv={self.point_de_vente.uuid}&tag_id_cm="
        for data_testid in ["header-tables", "menu-tables", "resto-action-table"]:
            position_testid = html.index(f'data-testid="{data_testid}"')
            debut_de_balise = max(html.rfind("<button", 0, position_testid), html.rfind("<a ", 0, position_testid))
            balise = html[debut_de_balise:position_testid]
            self.assertIn(lien_de_la_grille, balise, data_testid)
            self.assertNotIn("id_table=", balise, data_testid)
        self.assertIn('id="message-no-article"', html)
        self.assertNotIn("hx_get_all_tables", html)

    # ------------------------------------------------------------------ #
    #  Tuile « Nouvelle table » / "New table" tile
    # ------------------------------------------------------------------ #

    def _creer_une_table(self, nom):
        """POST de la tuile « Nouvelle table ». / POST from the "New table" tile."""
        return self.client_http.post(
            "/laboutik/caisse/ajouter_table/",
            data={
                "uuid_pv": str(self.point_de_vente.uuid),
                "tag_id_cm": "",
                "type_app": "unknown",
                "nouvelle_table": nom,
            },
        )

    def test_la_nouvelle_table_est_creee_et_choisie(self):
        """
        La table est creee en base, libre, ephemere. La reponse redirige
        vers l'ecran de cette table, qui s'affiche avec son nom.
        / The table is created and the response selects it.
        """
        reponse = self._creer_une_table("  Terrasse 4  ")

        table_creee = Table.objects.get(name="Terrasse 4")
        self.assertEqual(table_creee.statut, Table.LIBRE)
        self.assertTrue(table_creee.ephemere)
        self.assertEqual(reponse.status_code, 302)
        self.assertIn(f"id_table={table_creee.uuid}", reponse["Location"])

        ecran_de_la_table = self.client_http.get(reponse["Location"])
        self.assertTemplateUsed(ecran_de_la_table, "laboutik/views/common_user_interface.html")
        self.assertIn("Terrasse 4", ecran_de_la_table.content.decode())

    def test_un_nom_vide_donne_un_nom_automatique(self):
        """
        Nom vide : « Table N », sans collision avec une table existante.
        / Empty name: "Table N", never colliding with an existing table.
        """
        Table.objects.create(name="Table 1")

        self._creer_une_table("")

        self.assertTrue(Table.objects.filter(name="Table 2", statut=Table.LIBRE).exists())
        self.assertEqual(Table.objects.count(), 2)

    def test_un_nom_deja_pris_reprend_la_table_existante(self):
        """
        Nom deja pris : pas de doublon. Une table occupee garde son statut,
        une table archivee revient dans la grille.
        / Existing name: no duplicate; occupied stays, archived comes back.
        """
        table_occupee = Table.objects.create(name="Salon", statut=Table.OCCUPEE)
        table_archivee = Table.objects.create(name="Patio", archive=True)

        reponse_salon = self._creer_une_table("Salon")
        self._creer_une_table("Patio")

        table_occupee.refresh_from_db()
        table_archivee.refresh_from_db()
        self.assertEqual(Table.objects.count(), 2)
        self.assertEqual(table_occupee.statut, Table.OCCUPEE)
        self.assertIn(f"id_table={table_occupee.uuid}", reponse_salon["Location"])
        self.assertFalse(table_archivee.archive)

    def test_la_modale_poste_vers_ajouter_table(self):
        """
        La modale « Nouvelle table » poste vers la route ajouter_table.
        / The "new table" modal posts to the ajouter_table route.
        """
        reponse = self.client_http.get(
            "/laboutik/caisse/point_de_vente/",
            {"uuid_pv": str(self.point_de_vente.uuid)},
        )
        html = reponse.content.decode()

        self.assertIn('action="/laboutik/caisse/ajouter_table/"', html)
        self.assertIn('name="nouvelle_table"', html)
