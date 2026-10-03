"""
Migration de donnees : range les produits des contributions crowds dans la categorie
« Financement participatif », reliee au compte des dons (754000), dans chaque lieu.
/ Data migration: puts the crowds contribution products in the crowdfunding category,
linked to the donations account (754000), in every venue.

LOCALISATION : laboutik/migrations/0013_ranger_les_crowds_dans_le_financement_participatif.py

C'est la categorie qui donne le compte d'une contribution (laboutik/plan_comptable.py,
`compte_pour_article`, regle 2). Version « modeles historiques » (`apps.get_model`) de
l'etape 3 du chargeur de `laboutik/plan_comptable.py` : les lieux deja charges par la
migration 0010 ne repassent pas par le chargeur.
/ The category gives a contribution's account. Historical-models version of the
loader's step 3.

FLUX, idempotent (la rejouer ne change rien) :
1. Le 754000, cree s'il manque, avec les donnees du plan.
2. La categorie « Financement participatif », creee si elle manque, reliee au 754000
   si elle n'a pas de compte (un compte choisi par le lieu n'est pas touche).
3. Les produits « crowdfunding » sans categorie y sont ranges (un produit deja range
   ailleurs ne bouge pas).
"""

from django.db import connection, migrations

from laboutik.plan_comptable_par_defaut import (
    COMPTE_PAR_DEFAUT,
    COMPTES_DU_PLAN_PAR_DEFAUT,
    NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF,
    NOM_DU_PRODUIT_DE_FINANCEMENT_PARTICIPATIF,
)


def ranger_les_crowds_dans_le_financement_participatif(apps, schema_editor):
    """
    Cree et relie la categorie du financement participatif, puis y range les produits
    crowds sans categorie.
    / Creates and links the crowdfunding category, then files the crowds products.

    Les tables de `laboutik` et de `BaseBillet` (lieu) n'existent pas dans le schema
    `public` : rien a faire.
    / These tables do not exist in the public schema: nothing to do.
    """
    schema_courant = connection.schema_name
    if schema_courant == "public":
        return

    CompteComptable = apps.get_model("laboutik", "CompteComptable")
    CategorieProduct = apps.get_model("BaseBillet", "CategorieProduct")
    Product = apps.get_model("BaseBillet", "Product")

    # 1. Le compte des dons, cree s'il manque, avec les donnees du plan.
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

    # 2. La categorie. Son nom n'est pas unique en base : on prend la premiere.
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

    # 3. Les produits crowds sans categorie.
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


class Migration(migrations.Migration):
    dependencies = [
        ("BaseBillet", "0231_product_consigne_remboursee"),
        ("laboutik", "0012_relier_le_fed_au_compte_du_reseau"),
    ]

    operations = [
        migrations.RunPython(
            ranger_les_crowds_dans_le_financement_participatif,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
