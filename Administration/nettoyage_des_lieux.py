"""
Détection des lieux qui n'ont jamais eu aucune activité.
/ Detection of the venues that never had any activity.

LOCALISATION : Administration/nettoyage_des_lieux.py

Utilisé par la commande `manage.py supprimer_lieux_inactifs`
(Administration/management/commands/supprimer_lieux_inactifs.py).
Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md §18.
/ Used by the `supprimer_lieux_inactifs` command. Spec: §18.

UN LIEU EST INACTIF SI SES 8 CRITÈRES SONT VRAIS. Chaque critère faux donne une raison
qui garde le lieu. Une raison commence par le libellé du critère, puis une précision :
  1. « catégorie : … »                       (pool, agenda partagé, racine)
  2. « créé il y a moins de N jours »
  3. « activité dans le lieu : … »           (événements, ventes, adhésions…)
  4. « catalogue : … »                       (plus que le produit de l'onboarding)
  5. « table non vide : … »                  (table que personne ne remplit seul)
  6. « configuration personnalisée : … »     (champ différent du défaut du modèle)
  7. « trace dans les tables partagées : … » (cartes NFC, monnaies, droits…)
  8. « cité par un autre lieu : … »
  et « référence inconnue : … » : une ligne d'une table que l'outil ne sait pas nettoyer
  pointe vers le lieu.
/ A venue is inactive when its 8 criteria are true; each false criterion is a reason.

SQL BRUT SEULEMENT. La commande tourne la nuit de la bascule avec le code de la branche,
sur une base pas encore migrée (base de `main`). Aucun modèle n'est lu ni écrit : seul
`Configuration._meta` est lu, pour les défauts des champs (aucune requête). Une table ou
une colonne absente de la base est sautée.
/ Raw SQL only: must work before AND after the branch migrations. Only Configuration._meta
is read (no query). A missing table or column is skipped.

Les noms de schéma ne sortent jamais de ce module : un lieu est désigné par son domaine
principal.
/ Schema names never leave this module: a venue is named by its primary domain.
"""

from datetime import timedelta

from BaseBillet.models import Configuration

# --------------------------------------------------------------------------
# Critère 1 : les catégories jamais supprimées
# / Criterion 1: categories never deleted
# --------------------------------------------------------------------------

CATEGORIES_JAMAIS_SUPPRIMEES = {
    "W": "emplacement du pool",
    "M": "agenda partagé",
    "R": "racine",
}

# --------------------------------------------------------------------------
# Critère 3 : les tables d'activité du lieu
# / Criterion 3: the venue's activity tables
# --------------------------------------------------------------------------

# Une seule ligne dans l'une de ces tables suffit à garder le lieu.
# Les tables `crowds_*` (financement participatif) comptent aussi, sauf la
# configuration `crowds_crowdconfig` (créée à la première lecture).
# / One row in any of these tables keeps the venue. `crowds_*` tables too (except config).
TABLES_D_ACTIVITE = {
    "BaseBillet_event": "événements",
    "BaseBillet_reservation": "réservations",
    "BaseBillet_ticket": "billets",
    "BaseBillet_membership": "adhésions",
    "BaseBillet_lignearticle": "lignes de vente",
    "BaseBillet_vente": "ventes",
    "BaseBillet_reglement": "règlements",
    "BaseBillet_paiement_stripe": "paiements Stripe",
    "BaseBillet_productsold": "produits vendus",
    "BaseBillet_pricesold": "tarifs vendus",
    "BaseBillet_fedowtransaction": "transactions Fedow",
}
PREFIXE_DES_TABLES_DU_FINANCEMENT_PARTICIPATIF = "crowds_"
TABLE_DE_CONFIGURATION_DU_FINANCEMENT_PARTICIPATIF = "crowds_crowdconfig"

# --------------------------------------------------------------------------
# Critère 4 : le catalogue laissé par l'onboarding
# / Criterion 4: the catalogue left by onboarding
# --------------------------------------------------------------------------

# L'onboarding crée au plus un produit de réservation gratuite (catégorie « F ») avec un
# tarif à 0, et au plus une adresse.
# / Onboarding creates at most one free booking product (0 price) and one address.
TABLE_DES_PRODUITS = "BaseBillet_product"
TABLE_DES_TARIFS = "BaseBillet_price"
TABLE_DES_ADRESSES = "BaseBillet_postaladdress"
CATEGORIE_RESERVATION_GRATUITE = "F"

# --------------------------------------------------------------------------
# Critère 5 : les tables que la création du lieu ou les migrations remplissent seules
# / Criterion 5: tables filled on their own by venue creation or migrations
# --------------------------------------------------------------------------

# Établie sur un lieu neuf de la branche (schéma `test_modele`, créé par migrate_schemas)
# et sur les migrations de données de `main` (git show origin/main:<app>/migrations).
# Une ligne dans ces tables ne dit rien de l'activité du lieu.
# / Built from a fresh branch venue and from main's data migrations.
TABLES_REMPLIES_SEULES = {
    # Écrites par `migrate_schemas` dans chaque schéma.
    # / Written by migrate_schemas in every schema.
    "django_migrations": "historique des migrations",
    "django_content_type": "types de contenu, écrits par les migrations",
    # Migrations de données de BaseBillet (main et branche).
    # / BaseBillet data migrations.
    "BaseBillet_weekday": "jours de la semaine (BaseBillet 0086)",
    # Les taux semés par main 0187 seulement ; un autre taux garde le lieu (vérifié plus bas).
    # / Only the rates seeded by main 0187; another rate keeps the venue (checked below).
    "BaseBillet_tva": "taux de TVA par défaut (BaseBillet 0187)",
    "BaseBillet_categorieproduct": "catégorie « Financement participatif » (laboutik 0002)",
    # Singletons : une ligne écrite par l'onboarding, une migration, ou la première
    # lecture (`get_solo()`).
    # / Singletons: one row written by onboarding, a migration or the first read.
    "BaseBillet_federationconfiguration": "réglages de fédération (BaseBillet 0217, lecture)",
    "BaseBillet_ghostconfig": "réglages Ghost (lecture)",
    "BaseBillet_brevoconfig": "réglages Brevo (lecture)",
    "BaseBillet_formbricksconfig": "réglages Formbricks (lecture)",
    "fedow_connect_fedowconfig": "place Fedow, créée par l'onboarding",
    "crowds_crowdconfig": "réglages du financement participatif (lecture)",
    "pages_configurationsite": "réglages du site (lecture, branche)",
    "controlvanne_configurationtireuse": "réglages des tireuses (lecture, branche)",
    "laboutik_laboutikconfiguration": "réglages de la caisse et clé d'empreinte (laboutik 0002)",
    # Plans comptables semés par les migrations.
    # / Chart of accounts seeded by migrations.
    "comptabilite_comptecomptable": "plan comptable par défaut (main : comptabilite 0002)",
    "comptabilite_mappingmoyendepaiement": "correspondances par défaut (main : comptabilite 0002)",
    "laboutik_comptecomptable": "plan comptable par défaut (branche : laboutik 0002)",
    "laboutik_mappingmoyendepaiement": "correspondances par défaut (branche : laboutik 0002)",
    "laboutik_mappingmonnaie": "correspondance de la monnaie fédérée (branche : laboutik 0002)",
    # Clôtures automatiques : acceptées seulement à montant nul (vérifié plus bas).
    # / Automatic closures: accepted only with a zero amount (checked below).
    "comptabilite_cloturecaisse": "clôtures automatiques à montant nul",
    "laboutik_cloturecaisse": "clôtures automatiques à montant nul",
    # Page d'accueil par défaut : la migration BaseBillet 0225 la crée dans chaque lieu
    # qui a une configuration, par `pages.services.construire_page_accueil` : 1 page
    # d'accueil et au plus 3 blocs (bannière, texte, et un appel à l'action si la
    # billetterie ou les adhésions sont allumées). Rien de plus n'est accepté (vérifié
    # plus bas). `pages_imagegalerie` n'est pas dans la liste : une image garde le lieu.
    # / Default home page created by BaseBillet 0225: 1 home page, at most 3 blocks.
    "pages_page": "page d'accueil par défaut (BaseBillet 0225)",
    "pages_bloc": "blocs de la page d'accueil par défaut (BaseBillet 0225)",
    # Groupes de ressources par défaut : la migration booking 0003 crée dans chaque lieu
    # 2 groupes, « Ressource » et « Espace », sans description ni image. Rien de plus n'est
    # accepté (vérifié plus bas). Table de la branche seulement (booking n'est pas dans
    # main).
    # / Default resource groups seeded by booking 0003; nothing more is accepted.
    "booking_resourcegroup": "groupes de ressources par défaut (booking 0003)",
}

# Les 9 comptes du plan par défaut semé par `main:comptabilite/migrations/0002`.
# Un autre numéro dans `comptabilite_comptecomptable` est un compte ajouté par le lieu.
# / The 9 default accounts seeded by main's comptabilite 0002.
COMPTES_DU_PLAN_PAR_DEFAUT_DE_MAIN = [
    "411000",
    "4457100",
    "4457200",
    "4457300",
    "511000",
    "512000",
    "530000",
    "706000",
    "756000",
]
TABLES_DE_CLOTURES = ["comptabilite_cloturecaisse", "laboutik_cloturecaisse"]
TABLE_DES_PAGES = "pages_page"
TABLE_DES_BLOCS = "pages_bloc"
NOMBRE_DE_BLOCS_DE_L_ACCUEIL_PAR_DEFAUT = 3

# Les 6 taux semés par `main:BaseBillet/migrations/0187` (en texte, pour la requête).
# / The 6 rates seeded by main's BaseBillet 0187.
TABLE_DES_TAUX_DE_TVA = "BaseBillet_tva"
TAUX_DE_TVA_SEMES_PAR_MAIN = ["0.00", "2.10", "5.50", "8.50", "10.00", "20.00"]

# Les 2 groupes semés par `booking/migrations/0003_default_group`.
# / The 2 groups seeded by booking 0003.
TABLE_DES_GROUPES_DE_RESSOURCES = "booking_resourcegroup"
GROUPES_DE_RESSOURCES_SEMES_PAR_BOOKING = ["Ressource", "Espace"]

# --------------------------------------------------------------------------
# Critère 6 : la configuration
# / Criterion 6: the configuration
# --------------------------------------------------------------------------

TABLE_DE_LA_CONFIGURATION = "BaseBillet_configuration"

# Les colonnes que le formulaire de création remplit (nom, slug, email, descriptions,
# site, téléphone, Stripe Connect, adresse). Elles ne rendent pas le lieu actif.
# / Columns filled by the creation form: they do not make the venue active.
COLONNES_REMPLIES_A_LA_CREATION = [
    "id",
    "organisation",
    "slug",
    "email",
    "short_description",
    "long_description",
    "site_web",
    "phone",
    "stripe_connect_account",
    "stripe_connect_account_test",
    "stripe_mode_test",
    "postal_address_id",
    "adress",
    "postal_code",
    "city",
]

# Nom lisible de quelques colonnes, pour la raison. Les autres gardent leur nom.
# / Readable name of some columns; the others keep their name.
NOMS_LISIBLES_DES_COLONNES = {
    "logo": "logo",
    "img": "image",
    "server_cashless": "LaBoutik V1",
    "key_cashless": "LaBoutik V1",
    "stripe_payouts_enabled": "inscription Stripe terminée",
}

# L'habillage du site sur `main` : colonne `Configuration.skin`, défaut « reunion ».
# / The site skin on main: Configuration.skin, default "reunion".
COLONNE_DE_L_HABILLAGE_DE_MAIN = "skin"
HABILLAGE_PAR_DEFAUT_DE_MAIN = "reunion"

# Les réglages de newsletter et de formulaires : leur ligne est créée à la première lecture
# (d'où leur place dans `TABLES_REMPLIES_SEULES`), mais une colonne remplie veut dire que
# le lieu a branché le service : il est gardé. L'adresse de Formbricks (`api_host`) ne
# compte pas : elle a une valeur par défaut, remplie dans des centaines de lieux sans clé.
# / Newsletter and form settings: a filled column means the venue plugged the service in.
# The Formbricks host does not count (it has a default value).
REGLAGES_DES_SERVICES_BRANCHES = [
    ("BaseBillet_ghostconfig", ["ghost_key", "ghost_url"], "Ghost"),
    ("BaseBillet_brevoconfig", ["api_key"], "Brevo"),
    ("BaseBillet_formbricksconfig", ["api_key"], "Formbricks"),
]

# --------------------------------------------------------------------------
# Critères 7 et 8 : les références vers le lieu (lues dans le catalogue)
# / Criteria 7 and 8: references to the venue (read from the catalogue)
# --------------------------------------------------------------------------

# Les références du schéma public que l'outil nettoie lui-même. Elles ne gardent pas le
# lieu. `client_achat` n'est pas une preuve d'achat (toute connexion par email l'ajoute) ;
# les portefeuilles d'origine du lieu sont ceux des visiteurs connectés.
# / Public references the tool cleans itself: they do not keep the venue.
REFERENCES_QUE_L_OUTIL_NETTOIE = [
    ("Customers_domain", "tenant_id"),
    ("AuthBillet_tibilletuser", "client_source_id"),
    ("AuthBillet_tibilletuser_client_achat", "client_id"),
    ("AuthBillet_tibilletuser_client_admin", "client_id"),
    ("AuthBillet_wallet", "origin_id"),
    ("MetaBillet_waitingconfiguration", "tenant_id"),
    ("onboard_onboardinvitation", "invited_by_tenant_id"),
    ("seo_seocache", "tenant_id"),
]

# Critère 7 : les références du schéma public qui montrent une activité.
# Toutes les tables `fedow_core_*` (moteur V2) comptent aussi.
# / Criterion 7: public references showing activity. Every `fedow_core_*` table too.
REFERENCES_PARTAGEES_QUI_MONTRENT_UNE_ACTIVITE = {
    (
        "AuthBillet_tibilletuser_create_event",
        "client_id",
    ): "droit donné : créer des événements",
    (
        "AuthBillet_tibilletuser_initiate_payment",
        "client_id",
    ): "droit donné : lancer des paiements",
    (
        "AuthBillet_tibilletuser_manage_crowd",
        "client_id",
    ): "droit donné : financement participatif",
    ("QrcodeCashless_detail", "origine_id"): "cartes NFC",
    ("fedow_public_assetfedowpublic", "origin_id"): "monnaie Fedow créée",
    (
        "fedow_public_assetfedowpublic_federated_with",
        "client_id",
    ): "monnaie Fedow fédérée",
    (
        "fedow_public_assetfedowpublic_pending_invitations",
        "client_id",
    ): "invitation à une monnaie Fedow",
    ("MetaBillet_eventdirectory", "place_id"): "répertoire des événements",
    ("MetaBillet_eventdirectory", "artist_id"): "répertoire des événements",
    ("MetaBillet_productdirectory", "place_id"): "répertoire des produits",
    ("discovery_pairingdevice", "tenant_id"): "appareils appairés",
}
PREFIXE_DES_TABLES_DU_MOTEUR_V2 = "fedow_core_"

# Critère 8 : les tables d'un AUTRE lieu qui le citent.
# / Criterion 8: another venue's tables citing it.
REFERENCES_D_UN_AUTRE_LIEU = [
    ("BaseBillet_federatedplace", "tenant_id"),
    ("BaseBillet_configuration_federated_with", "client_id"),
    ("fedow_connect_asset_federated_with", "client_id"),
    ("fedow_connect_asset_invitation_to_federated_with", "client_id"),
    ("BaseBillet_artist_on_event", "artist_id"),
]

SCHEMA_PUBLIC = "public"


# --------------------------------------------------------------------------
# Outils SQL
# / SQL helpers
# --------------------------------------------------------------------------


def nom_sql(identifiant):
    """
    Un identifiant SQL entre guillemets doubles (schéma, table, colonne). Les noms du
    projet ont des majuscules (`BaseBillet_event`) : sans guillemets, PostgreSQL les met
    en minuscules et ne trouve pas la table.
    / A double-quoted SQL identifier (project names have capitals).
    """
    return '"' + identifiant.replace('"', '""') + '"'


def nom_complet(nom_du_schema, nom_de_la_table):
    """`"schema"."table"`, prêt pour une requête. / Ready for a query."""
    return f"{nom_sql(nom_du_schema)}.{nom_sql(nom_de_la_table)}"


def la_table_existe(curseur, nom_du_schema, nom_de_la_table):
    """
    Vrai si la table existe. `to_regclass` rend NULL pour une table absente, sans erreur.
    / True if the table exists (to_regclass returns NULL otherwise).
    """
    curseur.execute(
        "SELECT to_regclass(%s)", [nom_complet(nom_du_schema, nom_de_la_table)]
    )
    return curseur.fetchone()[0] is not None


def colonnes_de_la_table(curseur, nom_du_schema, nom_de_la_table):
    """
    Les noms des colonnes d'une table, lus dans le catalogue (liste vide si la table
    n'existe pas).
    / Column names of a table, from the catalogue.
    """
    curseur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        [nom_du_schema, nom_de_la_table],
    )
    noms_des_colonnes = []
    for (nom_de_la_colonne,) in curseur.fetchall():
        noms_des_colonnes.append(nom_de_la_colonne)
    return noms_des_colonnes


def le_schema_existe(curseur, nom_du_schema):
    """Vrai si le schéma existe. / True if the schema exists."""
    curseur.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", [nom_du_schema])
    return curseur.fetchone() is not None


# --------------------------------------------------------------------------
# Lecture des lieux et des références
# / Reading venues and references
# --------------------------------------------------------------------------


def lire_les_lieux(curseur):
    """
    Tous les lieux (sauf le schéma public), avec leur domaine principal (ou None).
    / Every venue (except the public schema), with its primary domain (or None).

    :return: liste de dictionnaires : uuid (texte), nom_du_schema, categorie,
        date_de_creation, domaine
    """
    # Lit chaque ligne `Client` et son domaine principal, s'il en a un.
    # / Reads every Client row and its primary domain, if any.
    curseur.execute(
        """
        SELECT lieu.uuid::text, lieu.schema_name, lieu.categorie, lieu.created_on,
               domaine.domain
        FROM public."Customers_client" lieu
        LEFT JOIN public."Customers_domain" domaine
            ON domaine.tenant_id = lieu.uuid AND domaine.is_primary
        WHERE lieu.schema_name <> %s
        ORDER BY domaine.domain
        """,
        [SCHEMA_PUBLIC],
    )
    lieux = []
    for (
        uuid_du_lieu,
        nom_du_schema,
        categorie,
        date_de_creation,
        domaine,
    ) in curseur.fetchall():
        lieux.append(
            {
                "uuid": uuid_du_lieu,
                "nom_du_schema": nom_du_schema,
                "categorie": categorie,
                "date_de_creation": date_de_creation,
                "domaine": domaine,
            }
        )
    return lieux


def lire_les_cles_etrangeres_vers_les_lieux(curseur):
    """
    Toutes les clés étrangères, dans tous les schémas, qui visent `Customers_client`.
    / Every foreign key, in every schema, targeting Customers_client.

    :return: liste de (nom_du_schema, nom_de_la_table, nom_de_la_colonne)
    """
    # Lit dans le catalogue PostgreSQL : la table qui pointe, son schéma, sa colonne.
    # / Reads from the PostgreSQL catalogue: pointing table, its schema, its column.
    curseur.execute(
        """
        SELECT espace.nspname, table_qui_pointe.relname, colonne_qui_pointe.attname
        FROM pg_constraint contrainte
        JOIN pg_class table_qui_pointe ON table_qui_pointe.oid = contrainte.conrelid
        JOIN pg_namespace espace ON espace.oid = table_qui_pointe.relnamespace
        JOIN pg_attribute colonne_qui_pointe
            ON colonne_qui_pointe.attrelid = contrainte.conrelid
            AND colonne_qui_pointe.attnum = contrainte.conkey[1]
        WHERE contrainte.contype = 'f'
          AND contrainte.confrelid = 'public."Customers_client"'::regclass
        ORDER BY 1, 2, 3
        """
    )
    return curseur.fetchall()


def compter_les_references_vers_les_lieux(curseur, cles_etrangeres, uuids_des_lieux):
    """
    Pour chaque lieu, les lignes qui pointent vers lui, table par table.
    / For each venue, the rows pointing to it, table by table.

    Une requête par clé étrangère, limitée aux lieux examinés.
    / One query per foreign key, limited to the examined venues.

    :return: dictionnaire uuid du lieu -> liste de (schema, table, colonne, nombre)
    """
    references_par_lieu = {}
    if not uuids_des_lieux:
        return references_par_lieu

    for nom_du_schema, nom_de_la_table, nom_de_la_colonne in cles_etrangeres:
        # Compte, pour chaque lieu examiné, les lignes de cette table qui le visent.
        # / Counts, for each examined venue, the rows of this table targeting it.
        curseur.execute(
            f"SELECT {nom_sql(nom_de_la_colonne)}::text, count(*) "
            f"FROM {nom_complet(nom_du_schema, nom_de_la_table)} "
            f"WHERE {nom_sql(nom_de_la_colonne)} = ANY(%s::uuid[]) "
            f"GROUP BY 1",
            [uuids_des_lieux],
        )
        for uuid_du_lieu, nombre_de_lignes in curseur.fetchall():
            if uuid_du_lieu not in references_par_lieu:
                references_par_lieu[uuid_du_lieu] = []
            references_par_lieu[uuid_du_lieu].append(
                (nom_du_schema, nom_de_la_table, nom_de_la_colonne, nombre_de_lignes)
            )
    return references_par_lieu


def lire_les_tables_non_vides(curseur, nom_du_schema):
    """
    Les tables du schéma du lieu qui ont au moins une ligne. Une seule requête : une
    branche `EXISTS` par table, réunies par `UNION ALL`.
    / The venue's non-empty tables, in a single UNION ALL query.
    """
    curseur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY tablename",
        [nom_du_schema],
    )
    noms_des_tables = []
    for (nom_de_la_table,) in curseur.fetchall():
        noms_des_tables.append(nom_de_la_table)
    if not noms_des_tables:
        return set()

    morceaux_de_la_requete = []
    parametres = []
    for nom_de_la_table in noms_des_tables:
        morceaux_de_la_requete.append(
            f"SELECT %s WHERE EXISTS "
            f"(SELECT 1 FROM {nom_complet(nom_du_schema, nom_de_la_table)})"
        )
        parametres.append(nom_de_la_table)
    curseur.execute(" UNION ALL ".join(morceaux_de_la_requete), parametres)

    tables_non_vides = set()
    for (nom_de_la_table,) in curseur.fetchall():
        tables_non_vides.add(nom_de_la_table)
    return tables_non_vides


def compter_les_lignes(curseur, nom_du_schema, nom_de_la_table, condition=""):
    """Nombre de lignes d'une table, avec une condition SQL facultative.
    / Row count of a table, with an optional SQL condition."""
    requete = f"SELECT count(*) FROM {nom_complet(nom_du_schema, nom_de_la_table)}"
    if condition:
        requete = requete + " WHERE " + condition
    curseur.execute(requete)
    return curseur.fetchone()[0]


# --------------------------------------------------------------------------
# Les critères
# / The criteria
# --------------------------------------------------------------------------


def raison_du_critere_1_categorie(lieu):
    """Critère 1 : pool, agenda partagé ou racine. / Criterion 1: category."""
    if lieu["categorie"] in CATEGORIES_JAMAIS_SUPPRIMEES:
        nom_de_la_categorie = CATEGORIES_JAMAIS_SUPPRIMEES[lieu["categorie"]]
        return [f"catégorie : {nom_de_la_categorie}"]
    return []


def raison_du_critere_2_age(lieu, jours_minimum, aujourd_hui):
    """Critère 2 : créé il y a plus de N jours. / Criterion 2: older than N days."""
    # « Plus de N jours » : un lieu créé il y a exactement N jours est encore gardé.
    # / "More than N days": a venue created exactly N days ago is still kept.
    date_limite = aujourd_hui - timedelta(days=jours_minimum)
    if lieu["date_de_creation"] >= date_limite:
        age_en_jours = (aujourd_hui - lieu["date_de_creation"]).days
        return [
            f"créé il y a moins de {jours_minimum} jours "
            f"(âge : {age_en_jours} jours ; il en faut plus de {jours_minimum})"
        ]
    return []


def raisons_du_critere_3_activite(curseur, nom_du_schema, tables_non_vides):
    """
    Critère 3 : aucune ligne dans les tables d'activité, ni dans le financement
    participatif.
    / Criterion 3: no row in the activity tables, nor in crowdfunding.
    """
    raisons = []
    for nom_de_la_table, nom_lisible in TABLES_D_ACTIVITE.items():
        if nom_de_la_table in tables_non_vides:
            nombre = compter_les_lignes(curseur, nom_du_schema, nom_de_la_table)
            raisons.append(f"activité dans le lieu : {nom_lisible} ({nombre})")

    for nom_de_la_table in sorted(tables_non_vides):
        est_une_table_du_financement_participatif = nom_de_la_table.startswith(
            PREFIXE_DES_TABLES_DU_FINANCEMENT_PARTICIPATIF
        )
        if not est_une_table_du_financement_participatif:
            continue
        if nom_de_la_table == TABLE_DE_CONFIGURATION_DU_FINANCEMENT_PARTICIPATIF:
            continue
        raisons.append(
            f"activité dans le lieu : financement participatif ({nom_de_la_table})"
        )
    return raisons


def raisons_du_critere_4_catalogue(curseur, nom_du_schema, tables_non_vides):
    """
    Critère 4 : au plus un produit, de réservation gratuite, tous les tarifs à 0, au plus
    une adresse.
    / Criterion 4: at most one free booking product, all prices at 0, at most one address.
    """
    raisons = []

    if TABLE_DES_PRODUITS in tables_non_vides:
        # Lit la catégorie de chaque produit du lieu.
        # / Reads the category of each product.
        curseur.execute(
            f"SELECT categorie_article FROM {nom_complet(nom_du_schema, TABLE_DES_PRODUITS)}"
        )
        categories_des_produits = []
        for (categorie,) in curseur.fetchall():
            categories_des_produits.append(categorie)
        if len(categories_des_produits) > 1:
            raisons.append(f"catalogue : {len(categories_des_produits)} produits")
        elif categories_des_produits[0] != CATEGORIE_RESERVATION_GRATUITE:
            raisons.append("catalogue : un produit autre qu'une réservation gratuite")

    if TABLE_DES_TARIFS in tables_non_vides:
        nombre_de_tarifs_non_nuls = compter_les_lignes(
            curseur, nom_du_schema, TABLE_DES_TARIFS, "prix <> 0"
        )
        if nombre_de_tarifs_non_nuls > 0:
            raisons.append(f"catalogue : tarifs non nuls ({nombre_de_tarifs_non_nuls})")

    if TABLE_DES_ADRESSES in tables_non_vides:
        nombre_d_adresses = compter_les_lignes(
            curseur, nom_du_schema, TABLE_DES_ADRESSES
        )
        if nombre_d_adresses > 1:
            raisons.append(f"catalogue : {nombre_d_adresses} adresses")

    return raisons


def raisons_du_critere_5_tables_non_vides(curseur, nom_du_schema, tables_non_vides):
    """
    Critère 5 : aucune autre table non vide que celles qui se remplissent seules.
    Les tables des critères 3, 4 et 6 sont jugées par leur critère.
    / Criterion 5: no other non-empty table than the self-filled ones.
    """
    tables_jugees_par_un_autre_critere = set(TABLES_D_ACTIVITE.keys())
    tables_jugees_par_un_autre_critere.add(TABLE_DES_PRODUITS)
    tables_jugees_par_un_autre_critere.add(TABLE_DES_TARIFS)
    tables_jugees_par_un_autre_critere.add(TABLE_DES_ADRESSES)
    tables_jugees_par_un_autre_critere.add(TABLE_DE_LA_CONFIGURATION)

    raisons = []
    for nom_de_la_table in sorted(tables_non_vides):
        if nom_de_la_table in tables_jugees_par_un_autre_critere:
            continue
        if nom_de_la_table.startswith(PREFIXE_DES_TABLES_DU_FINANCEMENT_PARTICIPATIF):
            if nom_de_la_table != TABLE_DE_CONFIGURATION_DU_FINANCEMENT_PARTICIPATIF:
                continue

        if nom_de_la_table not in TABLES_REMPLIES_SEULES:
            raisons.append(f"table non vide : {nom_de_la_table}")
            continue

        # Une clôture n'est acceptée qu'à montant nul et sans transaction.
        # / A closure is accepted only with a zero amount and no transaction.
        if nom_de_la_table in TABLES_DE_CLOTURES:
            colonnes = colonnes_de_la_table(curseur, nom_du_schema, nom_de_la_table)
            condition = "total_general <> 0"
            if "nombre_transactions" in colonnes:
                condition = condition + " OR nombre_transactions <> 0"
            if (
                compter_les_lignes(curseur, nom_du_schema, nom_de_la_table, condition)
                > 0
            ):
                raisons.append(
                    f"table non vide : {nom_de_la_table} (clôtures avec un montant)"
                )

        # Le plan comptable de main n'est accepté qu'avec ses 9 comptes par défaut.
        # / Main's chart of accounts is accepted only with its 9 default accounts.
        if nom_de_la_table == "comptabilite_comptecomptable":
            curseur.execute(
                f"SELECT count(*) FROM {nom_complet(nom_du_schema, nom_de_la_table)} "
                f"WHERE NOT (numero = ANY(%s))",
                [COMPTES_DU_PLAN_PAR_DEFAUT_DE_MAIN],
            )
            if curseur.fetchone()[0] > 0:
                raisons.append(
                    f"table non vide : {nom_de_la_table} (comptes ajoutés au plan par défaut)"
                )

        # Les taux de TVA ne sont acceptés que s'ils sont tous semés par main 0187.
        # / VAT rates are accepted only if all seeded by main 0187.
        if nom_de_la_table == TABLE_DES_TAUX_DE_TVA:
            curseur.execute(
                f"SELECT count(*) FROM {nom_complet(nom_du_schema, nom_de_la_table)} "
                f"WHERE NOT (tva_rate = ANY(%s::numeric[]))",
                [TAUX_DE_TVA_SEMES_PAR_MAIN],
            )
            if curseur.fetchone()[0] > 0:
                raisons.append(f"table non vide : {nom_de_la_table} (taux ajoutés)")

        # Les groupes de ressources ne sont acceptés que s'ils sont ceux de booking 0003 :
        # au plus 2, avec leur nom, sans description ni image.
        # / Resource groups are accepted only as seeded by booking 0003.
        if nom_de_la_table == TABLE_DES_GROUPES_DE_RESSOURCES:
            if groupes_de_ressources_ajoutes(curseur, nom_du_schema):
                raisons.append(f"table non vide : {nom_de_la_table} (groupes ajoutés)")

        # Les pages ne sont acceptées que si elles se réduisent à UNE page d'accueil.
        # / Pages are accepted only if there is exactly ONE home page.
        if nom_de_la_table == TABLE_DES_PAGES:
            nombre_de_pages = compter_les_lignes(
                curseur, nom_du_schema, TABLE_DES_PAGES
            )
            nombre_de_pages_d_accueil = compter_les_lignes(
                curseur, nom_du_schema, TABLE_DES_PAGES, "est_accueil"
            )
            if nombre_de_pages != 1 or nombre_de_pages_d_accueil != 1:
                raisons.append(
                    f"table non vide : {nom_de_la_table} (pages ajoutées à l'accueil par défaut)"
                )

        # Les blocs ne sont acceptés que sur la page d'accueil, et pas plus de 3.
        # / Blocks are accepted only on the home page, at most 3.
        if nom_de_la_table == TABLE_DES_BLOCS:
            nombre_de_blocs = compter_les_lignes(
                curseur, nom_du_schema, TABLE_DES_BLOCS
            )
            nombre_de_blocs_hors_de_l_accueil = compter_les_lignes(
                curseur,
                nom_du_schema,
                TABLE_DES_BLOCS,
                f"page_id NOT IN (SELECT uuid FROM "
                f"{nom_complet(nom_du_schema, TABLE_DES_PAGES)} WHERE est_accueil)",
            )
            if (
                nombre_de_blocs > NOMBRE_DE_BLOCS_DE_L_ACCUEIL_PAR_DEFAUT
                or nombre_de_blocs_hors_de_l_accueil > 0
            ):
                raisons.append(
                    f"table non vide : {nom_de_la_table} (blocs ajoutés à l'accueil par défaut)"
                )
    return raisons


def raisons_du_critere_6_services_branches(curseur, nom_du_schema, tables_non_vides):
    """
    Critère 6, suite : un service de newsletter ou de formulaires branché (Ghost, Brevo,
    Formbricks). Vide = NULL ou texte vide. Une colonne absente de la base est sautée.
    / Criterion 6, continued: a plugged-in newsletter or form service keeps the venue.
    """
    raisons = []
    for (
        nom_de_la_table,
        colonnes_a_lire,
        nom_du_service,
    ) in REGLAGES_DES_SERVICES_BRANCHES:
        if nom_de_la_table not in tables_non_vides:
            continue
        colonnes_de_la_base = colonnes_de_la_table(
            curseur, nom_du_schema, nom_de_la_table
        )

        conditions_de_colonne_remplie = []
        for nom_de_la_colonne in colonnes_a_lire:
            if nom_de_la_colonne in colonnes_de_la_base:
                conditions_de_colonne_remplie.append(
                    f"({nom_sql(nom_de_la_colonne)} IS NOT NULL "
                    f"AND {nom_sql(nom_de_la_colonne)} <> '')"
                )
        if not conditions_de_colonne_remplie:
            continue

        # Compte les lignes de réglages qui ont au moins une colonne remplie.
        # / Counts the settings rows with at least one filled column.
        nombre_de_lignes_remplies = compter_les_lignes(
            curseur,
            nom_du_schema,
            nom_de_la_table,
            " OR ".join(conditions_de_colonne_remplie),
        )
        if nombre_de_lignes_remplies > 0:
            raisons.append(f"configuration personnalisée : {nom_du_service}")
    return raisons


def groupes_de_ressources_ajoutes(curseur, nom_du_schema):
    """
    Vrai si les groupes de ressources du lieu ne sont plus exactement ceux semés par
    `booking 0003` : plus de 2 lignes, un autre nom, ou une description ou une image
    remplie. Une colonne absente est sautée.
    / True if the resource groups differ from those seeded by booking 0003.
    """
    nombre_de_groupes = compter_les_lignes(
        curseur, nom_du_schema, TABLE_DES_GROUPES_DE_RESSOURCES
    )
    if nombre_de_groupes > len(GROUPES_DE_RESSOURCES_SEMES_PAR_BOOKING):
        return True

    colonnes = colonnes_de_la_table(
        curseur, nom_du_schema, TABLE_DES_GROUPES_DE_RESSOURCES
    )
    conditions_d_un_groupe_modifie = ["NOT (name = ANY(%s))"]
    for nom_de_la_colonne in ["description", "image"]:
        if nom_de_la_colonne in colonnes:
            conditions_d_un_groupe_modifie.append(
                f"({nom_sql(nom_de_la_colonne)} IS NOT NULL "
                f"AND {nom_sql(nom_de_la_colonne)} <> '')"
            )
    # Compte les groupes qui ont un autre nom, ou une description ou une image.
    # / Counts the groups with another name, or a description or an image.
    curseur.execute(
        f"SELECT count(*) FROM "
        f"{nom_complet(nom_du_schema, TABLE_DES_GROUPES_DE_RESSOURCES)} "
        f"WHERE " + " OR ".join(conditions_d_un_groupe_modifie),
        [GROUPES_DE_RESSOURCES_SEMES_PAR_BOOKING],
    )
    return curseur.fetchone()[0] > 0


def valeur_normalisee(valeur):
    """Vide (None ou texte vide) devient None. / Empty becomes None."""
    if valeur is None or valeur == "":
        return None
    return valeur


def raisons_du_critere_6_configuration(curseur, nom_du_schema, tables_non_vides):
    """
    Critère 6 : chaque colonne de la configuration vaut le défaut du modèle, sauf celles
    du formulaire de création. Le défaut se lit dans `Configuration._meta` (aucune
    requête) ; une colonne absente de la base ou du modèle est sautée.
    / Criterion 6: every configuration column equals the model default, except the
    creation-form ones. Missing columns are skipped.
    """
    if TABLE_DE_LA_CONFIGURATION not in tables_non_vides:
        return []

    # Lit la ligne de configuration, colonne par colonne.
    # / Reads the configuration row, column by column.
    curseur.execute(
        f"SELECT * FROM {nom_complet(nom_du_schema, TABLE_DE_LA_CONFIGURATION)} LIMIT 1"
    )
    ligne = curseur.fetchone()
    valeur_par_colonne = {}
    for position, description_de_la_colonne in enumerate(curseur.description):
        valeur_par_colonne[description_de_la_colonne[0]] = ligne[position]

    noms_des_champs_personnalises = []
    for champ in Configuration._meta.concrete_fields:
        nom_de_la_colonne = champ.column
        if nom_de_la_colonne in COLONNES_REMPLIES_A_LA_CREATION:
            continue
        if nom_de_la_colonne not in valeur_par_colonne:
            continue
        if champ.has_default() and callable(champ.default):
            continue

        valeur_en_base = valeur_normalisee(valeur_par_colonne[nom_de_la_colonne])
        valeur_par_defaut = valeur_normalisee(champ.get_default())
        if valeur_en_base == valeur_par_defaut:
            continue

        nom_lisible = NOMS_LISIBLES_DES_COLONNES.get(
            nom_de_la_colonne, nom_de_la_colonne
        )
        if nom_lisible not in noms_des_champs_personnalises:
            noms_des_champs_personnalises.append(nom_lisible)

    # La colonne `skin` n'existe que sur `main` (la migration 0226 de la branche la retire) :
    # elle n'est donc pas dans `Configuration._meta`, son défaut est écrit ici.
    # / The `skin` column only exists on main (removed by the branch's 0226).
    if COLONNE_DE_L_HABILLAGE_DE_MAIN in valeur_par_colonne:
        habillage = valeur_normalisee(
            valeur_par_colonne[COLONNE_DE_L_HABILLAGE_DE_MAIN]
        )
        if habillage is not None and habillage != HABILLAGE_PAR_DEFAUT_DE_MAIN:
            noms_des_champs_personnalises.append("habillage (skin)")

    if noms_des_champs_personnalises:
        return [
            "configuration personnalisée : " + ", ".join(noms_des_champs_personnalises)
        ]
    return []


def nom_lisible_d_une_table(nom_du_schema, nom_de_la_table, domaine_par_schema):
    """
    Le nom d'une table pour une raison : le nom seul pour le schéma public, suivi du
    domaine de son lieu sinon (jamais le nom du schéma).
    / A table name for a reason: plus its venue's domain, never the schema name.
    """
    if nom_du_schema == SCHEMA_PUBLIC:
        return nom_de_la_table
    domaine_de_l_autre_lieu = domaine_par_schema.get(nom_du_schema)
    if domaine_de_l_autre_lieu is None:
        domaine_de_l_autre_lieu = "lieu sans domaine principal"
    return f"{nom_de_la_table} ({domaine_de_l_autre_lieu})"


def raisons_des_criteres_7_et_8_et_des_references_inconnues(
    lieu, references_du_lieu, domaine_par_schema
):
    """
    Critères 7 et 8, et les références inconnues, à partir des lignes qui pointent vers
    le lieu (lues dans le catalogue). Les lignes du schéma du lieu lui-même ne comptent
    pas ici : elles partent avec lui (le critère 5 les a déjà jugées).
    / Criteria 7 and 8 and unknown references, from the rows pointing to the venue.
    """
    raisons = []
    for nom_du_schema, nom_de_la_table, nom_de_la_colonne, nombre in references_du_lieu:
        if nom_du_schema == lieu["nom_du_schema"]:
            continue
        cle = (nom_de_la_table, nom_de_la_colonne)

        if nom_du_schema == SCHEMA_PUBLIC:
            if cle in REFERENCES_QUE_L_OUTIL_NETTOIE:
                continue
            if cle in REFERENCES_PARTAGEES_QUI_MONTRENT_UNE_ACTIVITE:
                precision = REFERENCES_PARTAGEES_QUI_MONTRENT_UNE_ACTIVITE[cle]
                raisons.append(
                    f"trace dans les tables partagées : {precision} ({nombre})"
                )
                continue
            if nom_de_la_table.startswith(PREFIXE_DES_TABLES_DU_MOTEUR_V2):
                raisons.append(
                    f"trace dans les tables partagées : moteur V2 ({nom_de_la_table})"
                )
                continue
        else:
            if cle in REFERENCES_D_UN_AUTRE_LIEU:
                nom_lisible = nom_lisible_d_une_table(
                    nom_du_schema, nom_de_la_table, domaine_par_schema
                )
                raisons.append(f"cité par un autre lieu : {nom_lisible}")
                continue

        nom_lisible = nom_lisible_d_une_table(
            nom_du_schema, nom_de_la_table, domaine_par_schema
        )
        raisons.append(f"référence inconnue : {nom_lisible}")
    return raisons


def raisons_qui_gardent_le_lieu(
    curseur, lieu, references_du_lieu, domaine_par_schema, jours_minimum, aujourd_hui
):
    """
    Toutes les raisons qui gardent le lieu. Liste vide = le lieu est inactif.
    / Every reason keeping the venue. Empty list = inactive venue.

    FLUX : critères 1 et 2 (ligne `Client`), puis 3 à 6 (schéma du lieu, lus en une
    requête pour les tables non vides), puis 7, 8 et références inconnues (catalogue).
    / Flow: criteria 1-2 (Client row), 3-6 (venue schema), 7-8 and unknown references.
    """
    raisons = []
    raisons.extend(raison_du_critere_1_categorie(lieu))
    raisons.extend(raison_du_critere_2_age(lieu, jours_minimum, aujourd_hui))

    nom_du_schema = lieu["nom_du_schema"]
    if not le_schema_existe(curseur, nom_du_schema):
        raisons.append("schéma absent")
        return raisons

    tables_non_vides = lire_les_tables_non_vides(curseur, nom_du_schema)
    raisons.extend(
        raisons_du_critere_3_activite(curseur, nom_du_schema, tables_non_vides)
    )
    raisons.extend(
        raisons_du_critere_4_catalogue(curseur, nom_du_schema, tables_non_vides)
    )
    raisons.extend(
        raisons_du_critere_5_tables_non_vides(curseur, nom_du_schema, tables_non_vides)
    )
    raisons.extend(
        raisons_du_critere_6_configuration(curseur, nom_du_schema, tables_non_vides)
    )
    raisons.extend(
        raisons_du_critere_6_services_branches(curseur, nom_du_schema, tables_non_vides)
    )
    raisons.extend(
        raisons_des_criteres_7_et_8_et_des_references_inconnues(
            lieu, references_du_lieu, domaine_par_schema
        )
    )
    return raisons


# --------------------------------------------------------------------------
# Lectures faites juste avant la suppression
# / Reads done right before deletion
# --------------------------------------------------------------------------


def lire_une_valeur_de_singleton(
    curseur, nom_du_schema, nom_de_la_table, nom_de_la_colonne
):
    """
    La valeur d'une colonne de la ligne unique d'une table, en texte ; texte vide si la
    table, la colonne ou la ligne manque.
    / A column value of a single-row table, as text; empty if missing.
    """
    if not la_table_existe(curseur, nom_du_schema, nom_de_la_table):
        return ""
    if nom_de_la_colonne not in colonnes_de_la_table(
        curseur, nom_du_schema, nom_de_la_table
    ):
        return ""
    curseur.execute(
        f"SELECT {nom_sql(nom_de_la_colonne)}::text "
        f"FROM {nom_complet(nom_du_schema, nom_de_la_table)} LIMIT 1"
    )
    ligne = curseur.fetchone()
    if ligne is None or ligne[0] is None:
        return ""
    return ligne[0]


def lire_les_traces_externes(curseur, nom_du_schema):
    """
    Ce que le lieu laisse hors de la base : comptes Stripe Connect et place Fedow.
    / What the venue leaves outside the database: Stripe Connect accounts, Fedow place.
    """
    return {
        "stripe_connect": lire_une_valeur_de_singleton(
            curseur, nom_du_schema, TABLE_DE_LA_CONFIGURATION, "stripe_connect_account"
        ),
        "stripe_connect_test": lire_une_valeur_de_singleton(
            curseur,
            nom_du_schema,
            TABLE_DE_LA_CONFIGURATION,
            "stripe_connect_account_test",
        ),
        "place_fedow": lire_une_valeur_de_singleton(
            curseur, nom_du_schema, "fedow_connect_fedowconfig", "fedow_place_uuid"
        ),
    }


def lire_les_adresses_des_administrateurs(curseur, uuid_du_lieu):
    """
    Les adresses email des administrateurs du lieu (`client_admin`).
    / The email addresses of the venue's administrators.
    """
    # Lit l'email de chaque utilisateur relié au lieu comme administrateur.
    # / Reads the email of each user linked to the venue as administrator.
    curseur.execute(
        """
        SELECT DISTINCT utilisateur.email
        FROM public."AuthBillet_tibilletuser" utilisateur
        JOIN public."AuthBillet_tibilletuser_client_admin" lien
            ON lien.tibilletuser_id = utilisateur.id
        WHERE lien.client_id = %s::uuid AND utilisateur.email <> ''
        ORDER BY utilisateur.email
        """,
        [uuid_du_lieu],
    )
    adresses = []
    for (adresse,) in curseur.fetchall():
        adresses.append(adresse)
    return adresses


def references_restantes_vers_le_lieu(curseur, uuid_du_lieu, domaine_par_schema):
    """
    Contrôle par le catalogue : les tables, dans tous les schémas, qui ont encore une
    ligne qui pointe vers le lieu. Une seule requête (`UNION ALL`). Liste vide = plus
    rien ne pointe vers le lieu.
    / Catalogue check: tables, in every schema, still pointing to the venue.
    """
    cles_etrangeres = lire_les_cles_etrangeres_vers_les_lieux(curseur)
    morceaux_de_la_requete = []
    parametres = []
    for nom_du_schema, nom_de_la_table, nom_de_la_colonne in cles_etrangeres:
        nom_lisible = nom_lisible_d_une_table(
            nom_du_schema, nom_de_la_table, domaine_par_schema
        )
        morceaux_de_la_requete.append(
            f"SELECT %s WHERE EXISTS (SELECT 1 FROM {nom_complet(nom_du_schema, nom_de_la_table)} "
            f"WHERE {nom_sql(nom_de_la_colonne)} = %s::uuid)"
        )
        parametres.append(nom_lisible)
        parametres.append(uuid_du_lieu)
    if not morceaux_de_la_requete:
        return []

    curseur.execute(" UNION ALL ".join(morceaux_de_la_requete), parametres)
    tables_restantes = []
    for (nom_lisible,) in curseur.fetchall():
        tables_restantes.append(nom_lisible)
    return tables_restantes
