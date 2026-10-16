"""
tests/pytest/test_api_v2_catalogue_comptable.py
Le catalogue de TiBillet tel qu'un logiciel comptable (Dolibarr) le recopie chaque nuit :
`GET /api/v2/products/?accounting=true`.
/ TiBillet's catalogue as an accounting software copies it every night.

LOCALISATION : tests/pytest/test_api_v2_catalogue_comptable.py

RÈGLES MÉTIER TESTÉES (spec TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-
comptables/CHANTIER-06-C-catalogue.md)
- Le droit : la route garde sa permission (droit « product ») ; la clé Dolibarr a les
  droits « product » ET « comptabilite » (C13).
- Sans `?accounting=true`, la réponse ne change pas : pas d'archivé, pas de propriété
  comptable.
- `?accounting=true` rend TOUS les produits (publiés ou non, archivés ou non) et TOUS
  leurs tarifs, avec, dans `additionalProperty` : le type, la catégorie de caisse, le
  taux de TVA effectif, le compte de vente (ou la phrase d'erreur), le booléen
  `forAccountingSync` et l'état archivé (§5.2).
- La TVA : celle du produit, sinon celle du lieu, JAMAIS celle de la catégorie ; 0 pour
  une recharge ; celle du gobelet pour un retour de consigne ; un retour de consigne sans
  gobelet ne fait pas planter le catalogue (§5.1).
- Le compte : la même règle que le FEC (catégorie de caisse, puis type de produit).
- `forAccountingSync` est faux pour ce qui n'est pas une vente (C6).
- L'`ETag` : le même tant que rien ne change, quelle que soit la langue du client ;
  `If-None-Match` égal → 304 sans corps ; un prix changé → un nouvel `ETag` (C10).
/ Business rules tested: key rights, unchanged default answer, the accounting
properties, VAT and account rules, the sync flag, the ETag.

Schéma dédié (`FastTenantTestCase`) : chaque test crée ses produits, effacés par le
rollback du test.
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

from decimal import Decimal  # noqa: E402

from django.db import connection  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from rest_framework_api_key.models import APIKey  # noqa: E402

from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    ExternalApiKey,
    Price,
    Product,
    Tva,
)
from BaseBillet.services_vente import NOM_ECART_RECU_EN_PLUS  # noqa: E402
from fabriques_panier import identifiant_unique  # noqa: E402
from laboutik.models import CompteComptable  # noqa: E402

DOMAINE_DU_LIEU_DE_TEST = "test-api-catalogue.tibillet.localhost"

ADRESSE_DU_CATALOGUE = "/api/v2/products/?accounting=true"


class TestApiCatalogueComptable(FastTenantTestCase):
    """
    Le catalogue comptable : droit, propriétés, TVA, compte, exclusions, ETag.
    / The accounting catalogue: right, properties, VAT, account, exclusions, ETag.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_api_catalogue"

    @classmethod
    def get_test_tenant_domain(cls):
        return DOMAINE_DU_LIEU_DE_TEST

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test API catalogue"

    def setUp(self):
        """
        Le lieu de test (TVA par défaut 10 %), la clé de Dolibarr (droits « product » et
        « comptabilite ») et le client HTTP.
        / The test venue (default VAT 10 %), Dolibarr's key and the HTTP client.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le cache de la configuration garde les valeurs du test précédent : on écrit
        # ici tout ce que le catalogue lit.
        # / The configuration cache survives: write everything the catalogue reads.
        configuration = Configuration.get_solo()
        configuration.vat_taxe = Decimal("10.00")
        configuration.save()

        self.cle_de_dolibarr = self._creer_une_cle_d_api(
            droit_produits=True, droit_comptabilite=True
        )

        self.client = APIClient()
        self.client.defaults["HTTP_HOST"] = DOMAINE_DU_LIEU_DE_TEST

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _creer_une_cle_d_api(self, droit_produits, droit_comptabilite):
        """
        Une clé d'API du lieu avec les droits demandés. Rend le texte de la clé.
        / A venue API key with the given rights; returns the key text.
        """
        nom_de_la_cle = f"catalogue-{identifiant_unique()}"
        cle_technique, texte_de_la_cle = APIKey.objects.create_key(name=nom_de_la_cle)
        ExternalApiKey.objects.create(
            name=nom_de_la_cle,
            key=cle_technique,
            product=droit_produits,
            comptabilite=droit_comptabilite,
        )
        return texte_de_la_cle

    def _lire(self, adresse=ADRESSE_DU_CATALOGUE, cle=None, **en_tetes):
        """
        Un GET de l'API avec la clé de Dolibarr (ou une autre clé).
        / A GET on the API with Dolibarr's key (or another key).
        """
        cle_a_utiliser = cle if cle is not None else self.cle_de_dolibarr
        return self.client.get(
            adresse, HTTP_AUTHORIZATION=f"Api-Key {cle_a_utiliser}", **en_tetes
        )

    def _taux(self, taux_en_texte):
        """La TVA de ce taux (unique en base). / The VAT row of this rate."""
        tva, _tva_creee = Tva.objects.get_or_create(tva_rate=Decimal(taux_en_texte))
        return tva

    def _creer_un_produit(self, nom, prix_en_euros="5.00", **champs_du_produit):
        """
        Un produit (nom rendu unique) et un tarif publié. Rend le produit.
        / A product (unique name) and one published price; returns the product.
        """
        produit = Product.objects.create(
            name=f"{nom} {identifiant_unique()}", **champs_du_produit
        )
        Price.objects.create(
            product=produit,
            name="Tarif unique",
            prix=Decimal(prix_en_euros),
            publish=True,
        )
        return produit

    def _categorie_de_caisse(self, numero_de_compte=None, taux_de_tva=None):
        """
        Une catégorie de caisse, reliée ou non à un compte et à une TVA.
        / A POS category, linked or not to an account and a VAT rate.
        """
        compte = None
        if numero_de_compte is not None:
            compte = CompteComptable.objects.get(numero_de_compte=numero_de_compte)
        tva = None
        if taux_de_tva is not None:
            tva = self._taux(taux_de_tva)
        return CategorieProduct.objects.create(
            name=f"Categorie {identifiant_unique()}",
            compte_comptable=compte,
            tva=tva,
        )

    def _produit_de_la_reponse(self, reponse, produit):
        """
        Le produit `produit` dans la réponse de la liste (ou None).
        / The product in the list response (or None).
        """
        for element in reponse.json()["results"]:
            if element["identifier"] == str(produit.uuid):
                return element
        return None

    def _propriete(self, element, nom):
        """
        La valeur de la propriété `nom` de `additionalProperty` (ou None si absente).
        / The value of an additionalProperty (or None when absent).
        """
        for propriete in element.get("additionalProperty", []):
            if propriete["name"] == nom:
                return propriete["value"]
        return None

    def _produit_du_catalogue(self, produit):
        """
        Le produit tel que le catalogue comptable le rend.
        / The product as the accounting catalogue returns it.
        """
        reponse = self._lire()
        assert reponse.status_code == 200, reponse.content
        element = self._produit_de_la_reponse(reponse, produit)
        assert element is not None, f"{produit.name} absent du catalogue"
        return element

    # ------------------------------------------------------------------
    # 1-2. Le droit et la réponse par défaut / The right and the default answer
    # ------------------------------------------------------------------

    def test_cle_produits_et_comptabilite_lit_le_catalogue_cle_comptable_seule_refusee(
        self,
    ):
        """
        La clé de Dolibarr (« product » + « comptabilite ») lit le catalogue. Une clé
        « comptabilite » seule reste refusée : la permission de la route ne change pas.
        / Dolibarr's key reads the catalogue; an accounting-only key is still refused.
        """
        cle_comptable_seule = self._creer_une_cle_d_api(
            droit_produits=False, droit_comptabilite=True
        )

        assert self._lire().status_code == 200
        assert self._lire(cle=cle_comptable_seule).status_code == 403

    def test_sans_accounting_la_reponse_ne_change_pas(self):
        """
        Sans `?accounting=true` : un produit archivé n'est pas rendu, et aucune
        propriété comptable n'apparaît.
        / Without the parameter: no archived product, no accounting property.
        """
        biere = self._creer_un_produit("Biere", methode_caisse=Product.VENTE)
        produit_archive = self._creer_un_produit("Ancien", archive=True)

        reponse = self._lire("/api/v2/products/")

        assert reponse.status_code == 200
        assert self._produit_de_la_reponse(reponse, produit_archive) is None
        element_de_la_biere = self._produit_de_la_reponse(reponse, biere)
        assert self._propriete(element_de_la_biere, "vatRate") is None
        assert self._propriete(element_de_la_biere, "forAccountingSync") is None

    # ------------------------------------------------------------------
    # 3. La TVA / VAT
    # ------------------------------------------------------------------

    def test_tva_du_produit_sinon_du_lieu_jamais_de_la_categorie(self):
        """
        Un produit à 5,5 % rend 5.50. Un produit sans TVA, dans une catégorie à 20 %,
        rend la TVA du lieu (10 %), pas celle de la catégorie.
        / Product VAT, else the venue's; never the category's.
        """
        categorie_a_vingt = self._categorie_de_caisse(taux_de_tva="20.00")
        livre = self._creer_un_produit("Livre", tva=self._taux("5.50"))
        sirop = self._creer_un_produit(
            "Sirop", methode_caisse=Product.VENTE, categorie_pos=categorie_a_vingt
        )

        assert self._propriete(self._produit_du_catalogue(livre), "vatRate") == "5.50"
        assert self._propriete(self._produit_du_catalogue(sirop), "vatRate") == "10.00"

    def test_tva_d_une_recharge_est_zero(self):
        """
        Une recharge est une dette, pas une vente : 0 %, même si le produit a une TVA.
        / A top-up is a debt, not a sale: 0 %.
        """
        recharge = self._creer_un_produit(
            "Recharge", methode_caisse=Product.RECHARGE_EUROS, tva=self._taux("20.00")
        )

        assert (
            self._propriete(self._produit_du_catalogue(recharge), "vatRate") == "0.00"
        )

    def test_tva_d_un_retour_de_consigne_est_celle_du_gobelet(self):
        """
        Un retour de consigne prend la TVA du gobelet qu'il rembourse. Sans gobelet
        relié, le catalogue répond quand même : ce produit porte une phrase d'erreur.
        / A deposit return takes the cup's VAT; without a cup, the catalogue still
        answers and the product carries an error sentence.
        """
        gobelet = self._creer_un_produit(
            "Gobelet", methode_caisse=Product.VENTE, tva=self._taux("20.00")
        )
        retour_relie = self._creer_un_produit(
            "Retour gobelet",
            methode_caisse=Product.RETOUR_CONSIGNE,
            consigne_remboursee=gobelet,
        )
        retour_orphelin = self._creer_un_produit(
            "Retour orphelin", methode_caisse=Product.RETOUR_CONSIGNE
        )

        element_relie = self._produit_du_catalogue(retour_relie)
        element_orphelin = self._produit_du_catalogue(retour_orphelin)

        assert self._propriete(element_relie, "vatRate") == "20.00"
        assert self._propriete(element_orphelin, "vatRate") is None
        assert self._propriete(element_orphelin, "vatRateError")

    # ------------------------------------------------------------------
    # 4. Le compte de vente / The sales account
    # ------------------------------------------------------------------

    def test_compte_de_la_categorie_de_caisse(self):
        """
        Un article de caisse rangé dans une catégorie reliée au 707000 : 707000.
        / A register item in a category linked to 707000.
        """
        categorie_bar = self._categorie_de_caisse(numero_de_compte="707000")
        biere = self._creer_un_produit(
            "Biere", methode_caisse=Product.VENTE, categorie_pos=categorie_bar
        )

        compte = self._propriete(self._produit_du_catalogue(biere), "accountingAccount")

        assert compte["number"] == "707000"

    def test_compte_par_le_type_billet_et_adhesion(self):
        """
        Sans catégorie de caisse, un billet va au 706000, une adhésion au 756000.
        / Without a POS category: ticket → 706000, membership → 756000.
        """
        billet = self._creer_un_produit("Billet", categorie_article=Product.BILLET)
        adhesion = self._creer_un_produit(
            "Adhesion", categorie_article=Product.ADHESION
        )

        compte_du_billet = self._propriete(
            self._produit_du_catalogue(billet), "accountingAccount"
        )
        compte_de_l_adhesion = self._propriete(
            self._produit_du_catalogue(adhesion), "accountingAccount"
        )

        assert compte_du_billet["number"] == "706000"
        assert compte_de_l_adhesion["number"] == "756000"

    def test_article_sans_type_porte_un_libelle_lisible(self):
        """
        Un article sans type (`N`, le défaut de tout article de caisse) a un libellé de
        type lisible : le logiciel comptable en fait une catégorie.
        / An untyped item (`N`) has a readable type label.
        """
        biere = self._creer_un_produit("Biere", methode_caisse=Product.VENTE)

        type_du_produit = self._propriete(self._produit_du_catalogue(biere), "productType")

        assert type_du_produit == {"code": Product.NONE, "label": "Article de caisse"}

    def test_article_de_caisse_sans_categorie_porte_une_phrase_d_erreur(self):
        """
        Un article de caisse sans catégorie de caisse n'a pas de compte : la réponse
        porte la phrase de la règle, et pas de compte.
        / A register item without a POS category: an error sentence, no account.
        """
        sirop = self._creer_un_produit("Sirop", methode_caisse=Product.VENTE)

        element = self._produit_du_catalogue(sirop)

        assert self._propriete(element, "accountingAccount") is None
        assert "catégorie de caisse" in self._propriete(
            element, "accountingAccountError"
        )

    # ------------------------------------------------------------------
    # 5. Ce qui va dans Dolibarr / What goes into Dolibarr
    # ------------------------------------------------------------------

    def test_for_accounting_sync_vrai_pour_les_ventes(self):
        """
        Une bière de caisse, un billet et un fût de tireuse sont des ventes en euros :
        la tireuse vend le fût lui-même, au litre (controlvanne/billing.py).
        / A register beer, a ticket and a tap keg are sales in euros: the tap sells the
        keg itself, per litre.
        """
        categorie_bar = self._categorie_de_caisse(numero_de_compte="707000")
        biere = self._creer_un_produit(
            "Biere", methode_caisse=Product.VENTE, categorie_pos=categorie_bar
        )
        billet = self._creer_un_produit("Billet", categorie_article=Product.BILLET)
        fut = self._creer_un_produit(
            "Fut", categorie_article=Product.FUT, categorie_pos=categorie_bar
        )

        for produit in [biere, billet, fut]:
            element = self._produit_du_catalogue(produit)
            assert self._propriete(element, "forAccountingSync") is True, produit.name

    def test_for_accounting_sync_faux_pour_ce_qui_n_est_pas_une_vente(self):
        """
        Recharge, virement reçu, retour de consigne, recharge en temps et écart
        d'encaissement ne vont pas dans Dolibarr.
        / Top-up, received transfer, deposit return, time top-up and cash gap are not
        sales.
        """
        produits_qui_ne_sont_pas_des_ventes = [
            self._creer_un_produit("Recharge", methode_caisse=Product.RECHARGE_EUROS),
            self._creer_un_produit("Virement", methode_caisse=Product.VIREMENT_RECU),
            self._creer_un_produit("Retour", methode_caisse=Product.RETOUR_CONSIGNE),
            self._creer_un_produit("Temps", methode_caisse=Product.RECHARGE_TEMPS),
        ]
        ecart = Product.objects.create(name=NOM_ECART_RECU_EN_PLUS)
        produits_qui_ne_sont_pas_des_ventes.append(ecart)

        for produit in produits_qui_ne_sont_pas_des_ventes:
            element = self._produit_du_catalogue(produit)
            assert self._propriete(element, "forAccountingSync") is False, produit.name

    # ------------------------------------------------------------------
    # 6. Archivés et non publiés / Archived and unpublished
    # ------------------------------------------------------------------

    def test_archives_et_non_publies_sont_rendus_avec_leur_etat(self):
        """
        Un produit archivé, un produit non publié et un tarif archivé sont rendus, avec
        `archived` à vrai pour ce qui est archivé.
        / Archived and unpublished products, and archived prices, are returned.
        """
        produit_archive = self._creer_un_produit("Ancien", archive=True)
        produit_non_publie = self._creer_un_produit("Cache", publish=False)
        produit_au_tarif_archive = self._creer_un_produit("Tarifs")
        tarif_archive = Price.objects.create(
            product=produit_au_tarif_archive, name="Ancien tarif", prix=Decimal("2.00")
        )
        tarif_archive.archived = True
        tarif_archive.save()

        element_archive = self._produit_du_catalogue(produit_archive)
        element_non_publie = self._produit_du_catalogue(produit_non_publie)
        element_aux_tarifs = self._produit_du_catalogue(produit_au_tarif_archive)

        assert self._propriete(element_archive, "archived") is True
        assert self._propriete(element_non_publie, "archived") is False
        offre_archivee = None
        for offre in element_aux_tarifs["offers"]:
            if offre["identifier"] == str(tarif_archive.uuid):
                offre_archivee = offre
        assert offre_archivee is not None
        assert self._propriete(offre_archivee, "archived") is True

    # ------------------------------------------------------------------
    # 7. L'ETag / The ETag
    # ------------------------------------------------------------------

    def test_etag_stable_puis_304_puis_nouveau_apres_un_changement_de_prix(self):
        """
        Deux appels sans changement : le même `ETag`. Avec `If-None-Match` : 304 sans
        corps. Un prix changé : un autre `ETag`.
        / Same ETag twice; 304 with If-None-Match; a new ETag after a price change.
        """
        biere = self._creer_un_produit("Biere", methode_caisse=Product.VENTE)

        premier_etag = self._lire()["ETag"]
        second_etag = self._lire()["ETag"]
        reponse_conditionnelle = self._lire(HTTP_IF_NONE_MATCH=premier_etag)

        tarif = biere.prices.get()
        tarif.prix = Decimal("6.00")
        tarif.save()
        etag_apres_le_changement = self._lire()["ETag"]

        assert premier_etag == second_etag
        assert reponse_conditionnelle.status_code == 304
        assert reponse_conditionnelle.content == b""
        assert etag_apres_le_changement != premier_etag

    def test_etag_faible_accepte_dans_if_none_match(self):
        """
        Un proxy qui compresse rend l'`ETag` « faible » (`W/"…"`) : le client le renvoie
        tel quel, et la réponse reste 304.
        / A compressing proxy makes the ETag weak; it is still accepted.
        """
        self._creer_un_produit("Biere", methode_caisse=Product.VENTE)
        etag = self._lire()["ETag"]

        reponse = self._lire(HTTP_IF_NONE_MATCH=f"W/{etag}")

        assert reponse.status_code == 304

    def test_etag_ne_depend_pas_de_la_langue_du_client(self):
        """
        Le catalogue contient des libellés traduits : il est rendu dans une langue fixe,
        donc l'`ETag` est le même en anglais et en français.
        / The catalogue is rendered in a fixed language: same ETag in English and French.
        """
        billet = self._creer_un_produit("Billet", categorie_article=Product.BILLET)

        etag_en_anglais = self._lire(HTTP_ACCEPT_LANGUAGE="en")["ETag"]
        etag_en_francais = self._lire(HTTP_ACCEPT_LANGUAGE="fr")["ETag"]

        assert etag_en_anglais == etag_en_francais
        # La langue fixe est le français. / The fixed language is French.
        type_du_billet = self._propriete(
            self._produit_de_la_reponse(self._lire(HTTP_ACCEPT_LANGUAGE="en"), billet),
            "productType",
        )
        assert type_du_billet["label"] == "Réservation de billets"

    def test_etag_change_avec_le_nom_l_archivage_et_le_compte(self):
        """
        Chaque changement que le logiciel comptable recopie donne un nouvel `ETag` : le
        nom du produit, son archivage, le compte de sa catégorie de caisse.
        / Each change the accounting software copies gives a new ETag.
        """
        categorie = self._categorie_de_caisse(numero_de_compte="707000")
        biere = self._creer_un_produit(
            "Biere", methode_caisse=Product.VENTE, categorie_pos=categorie
        )
        etags_vus = [self._lire()["ETag"]]

        biere.name = f"Biere blonde {identifiant_unique()}"
        biere.save()
        etags_vus.append(self._lire()["ETag"])

        biere.archive = True
        biere.save()
        etags_vus.append(self._lire()["ETag"])

        categorie.compte_comptable = CompteComptable.objects.get(numero_de_compte="706000")
        categorie.save()
        etags_vus.append(self._lire()["ETag"])

        assert len(set(etags_vus)) == 4, etags_vus

    def test_nombre_de_requetes_ne_grandit_pas_avec_les_tarifs(self):
        """
        Le catalogue est lu en un nombre fixe de requêtes, quel que soit le nombre de
        produits et de tarifs (adhésions obligatoires comprises) : il est recalculé à
        chaque appel, même pour répondre 304.
        / The catalogue is read in a fixed number of queries.
        """
        adhesion = self._creer_un_produit("Adhesion", categorie_article=Product.ADHESION)
        self._creer_un_produit("Biere", methode_caisse=Product.VENTE)
        self._lire()
        with CaptureQueriesContext(connection) as requetes_avant:
            self._lire()

        for numero in range(3):
            produit = self._creer_un_produit(f"Concert {numero}", categorie_article=Product.BILLET)
            for tarif in [produit.prices.get(), Price.objects.create(product=produit, name="Adherent", prix=Decimal("3.00"))]:
                tarif.adhesions_obligatoires.add(adhesion)
        with CaptureQueriesContext(connection) as requetes_apres:
            self._lire()

        assert len(requetes_apres) == len(requetes_avant), [
            requete["sql"][:120] for requete in requetes_apres.captured_queries
        ][-12:]
