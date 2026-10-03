"""
Les données du plan comptable par défaut. Rien d'autre : aucun modèle, aucune fonction.
/ The default chart of accounts data. Nothing else: no model, no function.

LOCALISATION : laboutik/plan_comptable_par_defaut.py

QUI LIT CE MODULE / WHO READS THIS MODULE
-----------------------------------------
- `laboutik/plan_comptable.py` : le chargeur (commande `charger_plan_comptable`, bouton
  de l'admin, filet `s_assurer_que_le_plan_existe`).
- `laboutik/migrations/0010_charger_le_plan_comptable_par_defaut.py` : la migration
  qui charge le plan dans tout lieu sans compte, y compris un lieu neuf
  (`auto_create_schema` rejoue les migrations).
- `laboutik/migrations/0012_relier_le_fed_au_compte_du_reseau.py` : le FED au 467000.
- `laboutik/migrations/0013_ranger_les_crowds_dans_le_financement_participatif.py` :
  la catégorie des crowds au 754000.
- `laboutik/plan_comptable.py` (règles de compte) et `comptabilite/ventilation.py`
  (la ventilation du FEC) ; `crowds/views.py` (catégorie du produit des
  contributions).

Une migration ne doit pas importer de modèle vivant : c'est pourquoi ce module ne
contient que des listes. Les natures sont écrites en toutes lettres (les valeurs de
`CompteComptable.NATURE_CHOICES`).
/ A migration must not import live models: this module only holds lists.

RÈGLE POUR LE LIEU : ajoutez des comptes, ne renumérotez pas ceux du plan par défaut.
Le chargeur retrouve ses comptes par leur numéro (et la TVA par son taux).
/ Venue rule: add accounts, do not renumber the default plan's accounts.

Les libellés sont des DONNÉES en base, comme un nom de produit : jamais `_()`.
/ Labels are database DATA: never `_()`.
"""

# --------------------------------------------------------------------------- #
#  Les comptes (numéros du plan comptable général, 6 chiffres)                #
#  The accounts (French general chart of accounts numbers, 6 digits)          #
# --------------------------------------------------------------------------- #
# `taux_de_tva` : le taux des comptes de TVA (le chargeur les cherche par ce taux,
# jamais par leur numéro). 707900 porte 0 : ventes réglées en jetons, hors TVA.
# / `taux_de_tva`: rate of VAT accounts (looked up by rate, never by number).

COMPTES_DU_PLAN_PAR_DEFAUT = [
    # Ventes / Sales
    {
        "numero": "706000",
        "libelle": "Prestations de services",
        "nature": "VENTE",
        "taux_de_tva": None,
    },
    {
        "numero": "707000",
        "libelle": "Ventes de marchandises",
        "nature": "VENTE",
        "taux_de_tva": None,
    },
    {
        "numero": "707900",
        "libelle": "Ventes réglées en jetons offerts, hors TVA",
        "nature": "VENTE",
        "taux_de_tva": "0.00",
    },
    {
        "numero": "756000",
        "libelle": "Cotisations",
        "nature": "VENTE",
        "taux_de_tva": None,
    },
    {
        "numero": "754000",
        "libelle": "Dons (financement participatif)",
        "nature": "VENTE",
        "taux_de_tva": None,
    },
    # TVA collectée, un compte par taux / Collected VAT, one account per rate
    {
        "numero": "445711",
        "libelle": "TVA collectée 20 %",
        "nature": "TVA",
        "taux_de_tva": "20.00",
    },
    {
        "numero": "445712",
        "libelle": "TVA collectée 10 %",
        "nature": "TVA",
        "taux_de_tva": "10.00",
    },
    {
        "numero": "445713",
        "libelle": "TVA collectée 5,5 %",
        "nature": "TVA",
        "taux_de_tva": "5.50",
    },
    {
        "numero": "445714",
        "libelle": "TVA collectée 2,1 %",
        "nature": "TVA",
        "taux_de_tva": "2.10",
    },
    # Trésorerie / Treasury
    {
        "numero": "530000",
        "libelle": "Caisse espèces",
        "nature": "TRESORERIE",
        "taux_de_tva": None,
    },
    {
        "numero": "511200",
        "libelle": "Chèques à encaisser",
        "nature": "TRESORERIE",
        "taux_de_tva": None,
    },
    {
        "numero": "512100",
        "libelle": "Carte bancaire (TPE)",
        "nature": "TRESORERIE",
        "taux_de_tva": None,
    },
    {
        "numero": "517100",
        "libelle": "Stripe (fonds en attente de virement)",
        "nature": "TRESORERIE",
        "taux_de_tva": None,
    },
    {
        "numero": "512000",
        "libelle": "Banque",
        "nature": "TRESORERIE",
        "taux_de_tva": None,
    },
    # Tiers / Third parties
    {
        "numero": "467000",
        "libelle": "Réseau fédéré (FED)",
        "nature": "TIERS",
        "taux_de_tva": None,
    },
    {
        "numero": "419100",
        "libelle": "Avances clients (recharges, monnaie locale, jetons offerts)",
        "nature": "TIERS",
        "taux_de_tva": None,
    },
    {
        "numero": "471000",
        "libelle": "Compte d'attente (à reclasser)",
        "nature": "TIERS",
        "taux_de_tva": None,
    },
    # Charges / Expenses
    {
        "numero": "623400",
        "libelle": "Cadeaux à la clientèle",
        "nature": "CHARGE",
        "taux_de_tva": None,
    },
    # Écarts d'encaissement / Collection gaps
    {
        "numero": "758000",
        "libelle": "Écart d'encaissement — reçu en plus",
        "nature": "PRODUIT_EXCEPTIONNEL",
        "taux_de_tva": None,
    },
    {
        "numero": "658000",
        "libelle": "Écart d'encaissement — reçu en moins",
        "nature": "CHARGE",
        "taux_de_tva": None,
    },
]


# --------------------------------------------------------------------------- #
#  Les comptes que les règles cherchent par leur numéro                        #
#  The accounts the rules look up by their number                              #
# --------------------------------------------------------------------------- #
# Lus par `laboutik/plan_comptable.py` (règles de compte, chargeur), par
# `comptabilite/ventilation.py` (la ventilation du FEC), par `crowds/views.py` et par
# les migrations `laboutik/0012` (FED) et `laboutik/0013` (crowds). Un lieu qui veut
# un autre compte pose une catégorie de caisse ; il ne renumérote pas ces comptes.
# / Read by the rules, the FEC breakdown, crowds and the 0012 / 0013 migrations.

COMPTE_PAR_DEFAUT = {
    "prestations": "706000",
    "cotisations": "756000",
    "dons": "754000",
    "avances_clients": "419100",
    "reseau_federe": "467000",
    "ecart_recu_en_plus": "758000",
    "ecart_recu_en_moins": "658000",
    # Jetons cadeau (D8 bis) : un jeton dépensé est une vente au 707900 ; des jetons
    # perdus au vidage annulent la dette au 623400.
    # / Gift tokens: spent → 707900; lost at card emptying → 623400.
    "ventes_reglees_en_jetons": "707900",
    "cadeaux_a_la_clientele": "623400",
}


# --------------------------------------------------------------------------- #
#  Les correspondances des moyens de paiement                                  #
#  The payment method mappings                                                 #
# --------------------------------------------------------------------------- #
# Aucune correspondance pour NA (offert) et NM (points) : pas d'écriture d'argent.
# Aucune pour SF (Stripe fédéré) : il passe toujours par le compte de sa monnaie.
# Aucune pour QR : aucun règlement ne porte ce moyen.
# / No mapping for NA, NM (no money entry), SF (goes through its currency's account)
# and QR (no payment carries it).

CORRESPONDANCES_DES_MOYENS_PAR_DEFAUT = [
    {"moyen": "CA", "libelle": "Espèces", "numero": "530000"},
    {"moyen": "CH", "libelle": "Chèque", "numero": "511200"},
    {"moyen": "CC", "libelle": "Carte bancaire (TPE)", "numero": "512100"},
    {"moyen": "SN", "libelle": "Stripe (en ligne)", "numero": "517100"},
    {"moyen": "SP", "libelle": "Stripe SEPA", "numero": "517100"},
    {"moyen": "SR", "libelle": "Stripe (paiement récurrent)", "numero": "517100"},
    {"moyen": "TR", "libelle": "Virement bancaire", "numero": "512000"},
    {"moyen": "LE", "libelle": "Monnaie locale du lieu", "numero": "419100"},
    {"moyen": "LG", "libelle": "Jetons offerts", "numero": "419100"},
    {"moyen": "UK", "libelle": "Moyen inconnu (à reclasser)", "numero": "471000"},
]


# --------------------------------------------------------------------------- #
#  Les catégories de caisse que le chargeur relie à un compte                  #
#  The POS categories the loader links to an account                           #
# --------------------------------------------------------------------------- #
# Le chargeur relie ces catégories SI elles existent et n'ont pas encore de compte.
# Il ne crée que celle du financement participatif ; les catégories d'écart et des
# jetons repris au vidage sont créées à la demande par `BaseBillet/services_vente.py`.
# / The loader links these categories IF they exist and have no account yet. It only
# creates the crowdfunding one; the gap and taken-back-token categories are created on
# demand.

NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF = "Financement participatif"

# Le nom du produit système des contributions crowds. `crowds/views.py`
# (`_get_or_create_crowdfunding_price`) le cherche par ce nom, sans tenir compte de la
# casse.
# / The name of the crowds contribution system product (looked up case-insensitively).
NOM_DU_PRODUIT_DE_FINANCEMENT_PARTICIPATIF = "crowdfunding"

# Recopie des noms de `BaseBillet/services_vente.py` (NOM_ECART_RECU_EN_PLUS /
# _EN_MOINS, NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE) : ce module n'importe rien. Les tests
# `test_categories_d_ecart_reliees_si_elles_existent` et
# `test_categorie_jetons_repris_reliee_au_623400` importent les constantes du
# service : si les deux copies divergent, ils échouent.
# / Copy of the names from services_vente.py: this module imports nothing. The tests
# import the service's constants and fail if both copies diverge.
NOM_CATEGORIE_ECART_RECU_EN_PLUS = "Écart d'encaissement — reçu en plus"
NOM_CATEGORIE_ECART_RECU_EN_MOINS = "Écart d'encaissement — reçu en moins"
NOM_CATEGORIE_JETONS_CADEAU_REPRIS_AU_VIDAGE = "Jetons cadeau repris au vidage"

COMPTE_DES_CATEGORIES_CONNUES = [
    {"nom_de_la_categorie": NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF, "numero": "754000"},
    {"nom_de_la_categorie": NOM_CATEGORIE_ECART_RECU_EN_PLUS, "numero": "758000"},
    {"nom_de_la_categorie": NOM_CATEGORIE_ECART_RECU_EN_MOINS, "numero": "658000"},
    {
        "nom_de_la_categorie": NOM_CATEGORIE_JETONS_CADEAU_REPRIS_AU_VIDAGE,
        "numero": "623400",
    },
]
