"""
Migration de données : prépare la caisse de chaque lieu.
/ Data migration: prepares each venue's POS.

LOCALISATION : laboutik/migrations/0002_preparer_chaque_lieu.py

Quatre étapes, dans cet ordre / Four steps, in this order:
1. `charger_le_plan_si_aucun_compte` : charge le plan comptable par défaut si le lieu
   n'a aucun compte.
   / Loads the default chart of accounts if the venue has no account.
2. `relier_le_fed_au_compte_du_reseau` : relie les deux uuid du FED au compte du
   réseau fédéré (467000).
   / Links both FED uuids to the federated network account (467000).
3. `ranger_les_crowds_dans_le_financement_participatif` : range les produits des
   contributions crowds dans la catégorie « Financement participatif » (754000).
   / Files the crowds contribution products in the crowdfunding category (754000).
4. `creer_la_configuration_et_sa_cle` : crée la ligne de `LaboutikConfiguration` et
   sa clé d'empreinte, en base.
   / Creates the LaboutikConfiguration row and its fingerprint key, in the database.

laboutik est une application de lieu : la migration tourne dans chaque schéma de lieu,
et à la création de chaque nouveau lieu (`Client.auto_create_schema = True` rejoue
toutes les migrations dans un schéma neuf). Chaque fonction ne fait rien dans le
schéma public (les tables n'y existent pas). Chaque fonction est idempotente : la
rejouer ne change rien.
/ Tenant app: runs in every venue schema and at each venue creation. Each function
does nothing in the public schema, and is idempotent.

Ces fonctions sont les versions « modèles historiques » (`apps.get_model`) du chargeur
de `laboutik/plan_comptable.py`. Elles n'importent que les DONNÉES du plan
(`laboutik/plan_comptable_par_defaut.py`), jamais un modèle vivant.
/ Historical-models versions of the loader. They import only the plan DATA.

Code repris tel quel des anciennes migrations de la branche :
`0010_charger_le_plan_comptable_par_defaut`, `0012_relier_le_fed_au_compte_du_reseau`,
`0013_ranger_les_crowds_dans_le_financement_participatif` et
`0016_cle_d_empreinte_toujours_en_base`.
/ Code taken as is from the former branch migrations 0010, 0012, 0013 and 0016.

Spécification de la clé d'empreinte :
TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-briefs/05-H-1-ter.md (point 8).
"""

import secrets

from django.db import connection, migrations

from laboutik.plan_comptable_par_defaut import (
    COMPTE_DES_CATEGORIES_CONNUES,
    COMPTE_PAR_DEFAUT,
    COMPTES_DU_PLAN_PAR_DEFAUT,
    CORRESPONDANCES_DES_MOYENS_PAR_DEFAUT,
    NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF,
    NOM_DU_PRODUIT_DE_FINANCEMENT_PARTICIPATIF,
)

# L'identifiant de la ligne unique de django-solo (`SingletonModel.singleton_instance_id`).
# / The django-solo single row id.
IDENTIFIANT_DE_LA_LIGNE_DU_SINGLETON = 1


# --------------------------------------------------------------------------- #
#  1. Le plan comptable par défaut / The default chart of accounts             #
# --------------------------------------------------------------------------- #


def charger_le_plan_si_aucun_compte(apps, schema_editor):
    """
    Charge le plan par défaut si le lieu n'a aucun compte. Sinon ne fait rien.
    / Loads the default plan if the venue has no account. Else does nothing.

    Le lieu n'ayant aucun compte, tout est créé d'un coup ; une correspondance de
    moyen déjà présente n'est pas touchée.
    / The venue has no account: everything is created at once; an existing payment
    method mapping is not touched.

    Les tables de `laboutik` n'existent pas dans le schéma `public` : rien à faire.
    / laboutik tables do not exist in the public schema: nothing to do.
    """
    schema_courant = connection.schema_name
    if schema_courant == "public":
        return

    CompteComptable = apps.get_model("laboutik", "CompteComptable")
    MappingMoyenDePaiement = apps.get_model("laboutik", "MappingMoyenDePaiement")
    CategorieProduct = apps.get_model("BaseBillet", "CategorieProduct")

    le_lieu_a_deja_un_compte = CompteComptable.objects.exists()
    if le_lieu_a_deja_un_compte:
        return

    # 1. Les comptes / The accounts
    compte_par_numero = {}
    for entree in COMPTES_DU_PLAN_PAR_DEFAUT:
        compte_par_numero[entree["numero"]] = CompteComptable.objects.create(
            numero_de_compte=entree["numero"],
            libelle_du_compte=entree["libelle"],
            nature_du_compte=entree["nature"],
            taux_de_tva=entree["taux_de_tva"],
        )

    # 2. Les correspondances des moyens, seulement si le moyen n'en a aucune
    # / 2. The payment method mappings, only if the method has none
    for correspondance in CORRESPONDANCES_DES_MOYENS_PAR_DEFAUT:
        le_moyen_a_deja_une_correspondance = MappingMoyenDePaiement.objects.filter(
            moyen_de_paiement=correspondance["moyen"]
        ).exists()
        if le_moyen_a_deja_une_correspondance:
            continue
        MappingMoyenDePaiement.objects.create(
            moyen_de_paiement=correspondance["moyen"],
            libelle_moyen=correspondance["libelle"],
            compte_de_tresorerie=compte_par_numero[correspondance["numero"]],
        )

    # 3. Les catégories connues, si elles existent et n'ont pas de compte
    # / 3. The known categories, if they exist and have no account
    for categorie_connue in COMPTE_DES_CATEGORIES_CONNUES:
        compte_de_la_categorie = compte_par_numero[categorie_connue["numero"]]
        categories_sans_compte = CategorieProduct.objects.filter(
            name=categorie_connue["nom_de_la_categorie"],
            compte_comptable__isnull=True,
        )
        for categorie in categories_sans_compte:
            categorie.compte_comptable = compte_de_la_categorie
            categorie.save(update_fields=["compte_comptable"])

    print(
        f"  -> [{schema_courant}] plan comptable par defaut charge "
        f"({len(COMPTES_DU_PLAN_PAR_DEFAUT)} comptes)"
    )


# --------------------------------------------------------------------------- #
#  2. Le FED et le compte du réseau fédéré / The FED and the network account   #
# --------------------------------------------------------------------------- #


def relier_le_fed_au_compte_du_reseau(apps, schema_editor):
    """
    Relie chaque uuid du FED au 467000, s'il n'a pas déjà de compte.
    / Links each FED uuid to 467000, if it has no account yet.

    Le FED a deux uuid : celui de `fedow_core.Asset` et celui de l'ancien Fedow
    (`fedow_public.AssetFedowPublic`). Un règlement `SF` passe toujours par le compte
    de sa monnaie (laboutik/plan_comptable.py, `compte_pour_reglement`). Le 467000
    est créé s'il manque ; une correspondance existante n'est pas touchée.
    / The FED has two uuids. An SF payment always goes through its currency's
    account. 467000 is created if missing; an existing mapping is not touched.

    Les monnaies vivent dans le schéma `public` (SHARED_APPS) : le schéma d'un lieu
    les voit par son `search_path`.
    / Currencies live in the public schema: a venue's schema sees them via search_path.

    Les tables de `laboutik` n'existent pas dans le schéma `public` : rien à faire.
    / laboutik tables do not exist in the public schema: nothing to do.
    """
    schema_courant = connection.schema_name
    if schema_courant == "public":
        return

    CompteComptable = apps.get_model("laboutik", "CompteComptable")
    MappingMonnaie = apps.get_model("laboutik", "MappingMonnaie")
    Asset = apps.get_model("fedow_core", "Asset")
    AssetFedowPublic = apps.get_model("fedow_public", "AssetFedowPublic")

    # Le compte du réseau fédéré, créé s'il manque, avec les données du plan.
    # / The federated network account, created if missing, from the plan data.
    numero_du_reseau_federe = COMPTE_PAR_DEFAUT["reseau_federe"]
    entree_du_reseau_federe = None
    for entree in COMPTES_DU_PLAN_PAR_DEFAUT:
        if entree["numero"] == numero_du_reseau_federe:
            entree_du_reseau_federe = entree
    compte_du_reseau_federe, _compte_cree = CompteComptable.objects.get_or_create(
        numero_de_compte=numero_du_reseau_federe,
        defaults={
            "libelle_du_compte": entree_du_reseau_federe["libelle"],
            "nature_du_compte": entree_du_reseau_federe["nature"],
            "taux_de_tva": entree_du_reseau_federe["taux_de_tva"],
        },
    )

    # Les deux uuid du FED (« FED » : même code de catégorie dans les deux moteurs).
    # / Both FED uuids ("FED": same category code in both engines).
    uuids_du_fed = []
    for fed_de_fedow_core in Asset.objects.filter(category="FED"):
        uuids_du_fed.append(fed_de_fedow_core.uuid)
    for fed_de_l_ancien_fedow in AssetFedowPublic.objects.filter(category="FED"):
        uuids_du_fed.append(fed_de_l_ancien_fedow.uuid)

    nombre_de_correspondances_creees = 0
    for uuid_du_fed in uuids_du_fed:
        _correspondance, correspondance_creee = MappingMonnaie.objects.get_or_create(
            asset_uuid=uuid_du_fed,
            defaults={"compte_de_tresorerie": compte_du_reseau_federe},
        )
        if correspondance_creee:
            nombre_de_correspondances_creees += 1

    if nombre_de_correspondances_creees:
        print(
            f"  -> [{schema_courant}] FED relie au {numero_du_reseau_federe} "
            f"({nombre_de_correspondances_creees} uuid)"
        )


# --------------------------------------------------------------------------- #
#  3. Les crowds dans le financement participatif / Crowds in crowdfunding     #
# --------------------------------------------------------------------------- #


def ranger_les_crowds_dans_le_financement_participatif(apps, schema_editor):
    """
    Crée et relie la catégorie du financement participatif, puis y range les produits
    crowds sans catégorie.
    / Creates and links the crowdfunding category, then files the crowds products.

    C'est la catégorie qui donne le compte d'une contribution
    (laboutik/plan_comptable.py, `compte_pour_article`, règle 2).
    / The category gives a contribution's account.

    FLUX, idempotent (la rejouer ne change rien) :
    1. Le 754000, créé s'il manque, avec les données du plan.
    2. La catégorie « Financement participatif », créée si elle manque, reliée au
       754000 si elle n'a pas de compte (un compte choisi par le lieu n'est pas touché).
    3. Les produits « crowdfunding » sans catégorie y sont rangés (un produit déjà
       rangé ailleurs ne bouge pas).

    Les tables de `laboutik` et de `BaseBillet` (lieu) n'existent pas dans le schéma
    `public` : rien à faire.
    / These tables do not exist in the public schema: nothing to do.
    """
    schema_courant = connection.schema_name
    if schema_courant == "public":
        return

    CompteComptable = apps.get_model("laboutik", "CompteComptable")
    CategorieProduct = apps.get_model("BaseBillet", "CategorieProduct")
    Product = apps.get_model("BaseBillet", "Product")

    # 1. Le compte des dons, créé s'il manque, avec les données du plan.
    # / 1. The donations account, created if missing, from the plan data.
    numero_des_dons = COMPTE_PAR_DEFAUT["dons"]
    entree_des_dons = None
    for entree in COMPTES_DU_PLAN_PAR_DEFAUT:
        if entree["numero"] == numero_des_dons:
            entree_des_dons = entree
    compte_des_dons, _compte_cree = CompteComptable.objects.get_or_create(
        numero_de_compte=numero_des_dons,
        defaults={
            "libelle_du_compte": entree_des_dons["libelle"],
            "nature_du_compte": entree_des_dons["nature"],
            "taux_de_tva": entree_des_dons["taux_de_tva"],
        },
    )

    # 2. La catégorie. Son nom n'est pas unique en base : on prend la première.
    # / 2. The category. Its name is not unique: take the first one.
    categorie_financement_participatif = CategorieProduct.objects.filter(
        name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
    ).first()
    if categorie_financement_participatif is None:
        categorie_financement_participatif = CategorieProduct.objects.create(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF,
            compte_comptable=compte_des_dons,
        )
    elif categorie_financement_participatif.compte_comptable_id is None:
        categorie_financement_participatif.compte_comptable = compte_des_dons
        categorie_financement_participatif.save(update_fields=["compte_comptable"])

    # 3. Les produits crowds sans catégorie.
    # / 3. The crowds products without category.
    nombre_de_produits_ranges = Product.objects.filter(
        name__iexact=NOM_DU_PRODUIT_DE_FINANCEMENT_PARTICIPATIF,
        categorie_pos__isnull=True,
    ).update(categorie_pos=categorie_financement_participatif)

    if nombre_de_produits_ranges:
        print(
            f"  -> [{schema_courant}] {nombre_de_produits_ranges} produit(s) crowds "
            f"range(s) dans « {NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF} »"
        )


# --------------------------------------------------------------------------- #
#  4. La clé d'empreinte du lieu / The venue's fingerprint key                 #
# --------------------------------------------------------------------------- #


def creer_la_configuration_et_sa_cle(apps, schema_editor):
    """
    Crée la ligne de `LaboutikConfiguration` si elle manque, et sa clé d'empreinte si
    elle est vide. Même génération et même chiffrement que
    `LaboutikConfiguration.get_or_create_hmac_key` : 32 octets en hexadécimal,
    chiffrés Fernet. N'utilise pas `schema_editor`.
    / Creates the row if missing and its key if empty (same generation and encryption
    as get_or_create_hmac_key). Does not use schema_editor.

    POURQUOI : la clé d'empreinte (HMAC) scelle chaque vente réglée. Elle vit dans
    `LaboutikConfiguration.hmac_key`, un singleton django-solo mis en cache
    (memcached). Sans cette étape, la ligne n'est créée qu'au premier `get_solo()`.
    Si cette première création a lieu dans une transaction annulée ensuite, le cache
    garde un objet que la base n'a pas (tests/PIEGES.md 9.86). Avec la ligne et la clé
    déjà en base, la première vente n'a rien à créer.
    / WHY: without this step, the row is created at the first get_solo(); inside a
    rolled back transaction, the cache keeps an object the database does not have.

    Une clé existante ne change JAMAIS : changer la clé casserait la vérification des
    empreintes déjà écrites.
    / An existing key NEVER changes.
    """
    # Le schéma public n'a pas la table : on ne fait rien.
    # / The public schema has no such table: do nothing.
    schema_courant = connection.schema_name
    if schema_courant == "public":
        return

    from root_billet.utils import fernet_encrypt

    LaboutikConfiguration = apps.get_model("laboutik", "LaboutikConfiguration")
    configuration_du_lieu, _ligne_creee = LaboutikConfiguration.objects.get_or_create(
        pk=IDENTIFIANT_DE_LA_LIGNE_DU_SINGLETON
    )

    cle_deja_presente = bool(configuration_du_lieu.hmac_key)
    if cle_deja_presente:
        return

    nouvelle_cle = secrets.token_hex(32)
    LaboutikConfiguration.objects.filter(
        pk=IDENTIFIANT_DE_LA_LIGNE_DU_SINGLETON
    ).update(hmac_key=fernet_encrypt(nouvelle_cle))
    print(f"  -> [{schema_courant}] clé d'empreinte du lieu créée")


class Migration(migrations.Migration):

    dependencies = [
        ("laboutik", "0001_initial"),
        # CategorieProduct.compte_comptable et Product.categorie_pos.
        # / CategorieProduct.compte_comptable and Product.categorie_pos.
        ("BaseBillet", "0224_liens_caisse_fedow_et_montants_des_ventes"),
        # Les deux uuid du FED / Both FED uuids.
        ("fedow_core", "0001_initial"),
        ("fedow_public", "0004_libelles_fr_des_monnaies"),
    ]

    operations = [
        migrations.RunPython(
            charger_le_plan_si_aucun_compte,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            relier_le_fed_au_compte_du_reseau,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            ranger_les_crowds_dans_le_financement_participatif,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            creer_la_configuration_et_sa_cle,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
