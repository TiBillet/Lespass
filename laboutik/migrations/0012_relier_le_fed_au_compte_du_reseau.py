"""
Migration de donnees : relie les deux uuid du FED au compte du reseau federe (467000)
dans chaque lieu.
/ Data migration: links both FED uuids to the federated network account (467000) in
every venue.

LOCALISATION : laboutik/migrations/0012_relier_le_fed_au_compte_du_reseau.py

Le FED a deux uuid : celui de `fedow_core.Asset` et celui de l'ancien Fedow
(`fedow_public.AssetFedowPublic`). Un reglement `SF` passe toujours par le compte de sa
monnaie (laboutik/plan_comptable.py, `compte_pour_reglement`).
/ The FED has two uuids. An SF payment always goes through its currency's account.

C'est la version « modeles historiques » (`apps.get_model`) de l'etape 4 du chargeur
de `laboutik/plan_comptable.py` : les lieux deja charges par la migration 0010 ne
repassent pas par le chargeur. Comme lui, elle cree le 467000 s'il manque et ne touche
pas une correspondance existante : la rejouer ne change rien.
/ Historical-models version of the loader's step 4. Idempotent.

Les monnaies vivent dans le schema `public` (SHARED_APPS) : le schema d'un lieu les
voit par son `search_path`.
/ Currencies live in the public schema: a venue's schema sees them via search_path.
"""

from django.db import connection, migrations

from laboutik.plan_comptable_par_defaut import (
    COMPTE_PAR_DEFAUT,
    COMPTES_DU_PLAN_PAR_DEFAUT,
)


def relier_le_fed_au_compte_du_reseau(apps, schema_editor):
    """
    Relie chaque uuid du FED au 467000, s'il n'a pas deja de compte.
    / Links each FED uuid to 467000, if it has no account yet.

    Les tables de `laboutik` n'existent pas dans le schema `public` : rien a faire.
    / laboutik tables do not exist in the public schema: nothing to do.
    """
    schema_courant = connection.schema_name
    if schema_courant == "public":
        return

    CompteComptable = apps.get_model("laboutik", "CompteComptable")
    MappingMonnaie = apps.get_model("laboutik", "MappingMonnaie")
    Asset = apps.get_model("fedow_core", "Asset")
    AssetFedowPublic = apps.get_model("fedow_public", "AssetFedowPublic")

    # Le compte du reseau federe, cree s'il manque, avec les donnees du plan.
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

    # Les deux uuid du FED (« FED » : meme code de categorie dans les deux moteurs).
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


class Migration(migrations.Migration):
    dependencies = [
        ("fedow_core", "0001_initial"),
        ("fedow_public", "0004_verbose_name_fr"),
        ("laboutik", "0011_monnaie_et_code_journal"),
    ]

    operations = [
        migrations.RunPython(
            relier_le_fed_au_compte_du_reseau,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
