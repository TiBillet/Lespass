"""
Verification de depart des moteurs de monnaie de la base de dev.
/ Start-up check of the dev database's currency engines.

LOCALISATION : tests/outils_moteur_de_monnaie.py

Specs : TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md §7
et 14-spec-tests-federation-inter-lieux.md §2.

Deux verifications :
- `verifier_le_depart_de_la_suite()` : LEGERE (une requete). Appliquee a TOUTE la suite
  pytest par la fixture autouse `_moteurs_verifies_au_depart_de_la_suite`
  (tests/pytest/conftest.py) ;
- `verifier_les_moteurs_de_depart()` : COMPLETE (lieux de demo compris). A la demande :
  fixture `moteurs_de_depart_verifies`, dans tests/pytest/conftest.py et dans
  tests/e2e/conftest.py (meme nom).
/ A light check applied to the whole pytest suite, and a full check on demand.

ACCES A LA BASE : les deux fonctions lisent la table `Customers_client` (schema public).
L'appelant doit autoriser l'acces a la base :
- en pytest : un test marque `django_db`, ou `django_db_blocker.unblock()` (fixture
  autouse de portee session) ;
- en E2E : `django_db_blocker.unblock()` (pas de rollback contre un serveur reel).
/ DB access: the caller must allow it (django_db mark, or django_db_blocker.unblock()).
"""

import pytest
from django.db.models import Q

# La consigne quand un lieu `test_*` est en `legacy` : il a ete cree avant la migration
# `Customers 0006`. Les tests de caisse V2, de kiosk et de tireuse tomberaient sur le verrou.
# / What to do when a `test_*` venue is legacy: it predates the Customers 0006 migration.
CONSIGNE_POUR_LES_LIEUX_DE_TEST_EN_LEGACY = (
    "ils ont ete crees avant la migration Customers 0006. Au choix (accord du "
    "mainteneur) : repartir d'une base neuve (`docker compose down -v`, puis le flush de "
    "la demo), ou passer leurs lignes en v2 : UPDATE public.\"Customers_client\" SET "
    "moteur_monnaie = 'v2' WHERE schema_name LIKE 'test\\_%'; (skill tibillet-test, §3)."
)


def verifier_le_depart_de_la_suite():
    """
    Verification LEGERE, appliquee a toute la suite pytest : echoue, avec la consigne, si
    une ligne `Client` `test_*` est `legacy` ou si `lespass` n'est pas `v2`.
    / LIGHT check for the whole pytest suite: fails, with what to do, if a `test_*`
    venue is legacy or if `lespass` is not v2.

    LOCALISATION : tests/outils_moteur_de_monnaie.py

    APPELEE PAR : la fixture autouse de portee session
    `_moteurs_verifies_au_depart_de_la_suite` (tests/pytest/conftest.py).

    UNE seule requete sur `Customers_client` : elle tourne au depart de chaque lancement
    de pytest, meme pour un seul test. Les lieux de demo (`festival` legacy...) ne sont
    PAS verifies ici : c'est `verifier_les_moteurs_de_depart()`, a la demande.
    Jamais de `skip` : un etat faux doit se voir.
    / One query only; demo venues are checked on demand by the full check.
    """
    from Customers.models import Client

    lignes_a_verifier = Client.objects.filter(
        Q(schema_name="lespass")
        | Q(schema_name__startswith="test_", moteur_monnaie=Client.MOTEUR_LEGACY)
    ).values_list("schema_name", "moteur_monnaie")

    problemes_trouves = []
    moteur_de_lespass = None
    noms_des_lieux_de_test_en_legacy = []
    for nom_du_schema, moteur_du_lieu in lignes_a_verifier:
        if nom_du_schema == "lespass":
            moteur_de_lespass = moteur_du_lieu
        else:
            noms_des_lieux_de_test_en_legacy.append(nom_du_schema)

    if moteur_de_lespass is None:
        problemes_trouves.append(
            "le lieu `lespass` n'existe pas (relancer la demo : demo_data_v2)"
        )
    elif moteur_de_lespass != Client.MOTEUR_V2:
        problemes_trouves.append(
            f"le lieu `lespass` est `{moteur_de_lespass}`, `v2` attendu (verifier la "
            f"migration BaseBillet 0227 et la demo demo_data_v2)"
        )

    if noms_des_lieux_de_test_en_legacy:
        problemes_trouves.append(
            f"{len(noms_des_lieux_de_test_en_legacy)} lieu(x) `test_*` en `legacy` "
            f"({', '.join(sorted(noms_des_lieux_de_test_en_legacy))}) : "
            f"{CONSIGNE_POUR_LES_LIEUX_DE_TEST_EN_LEGACY}"
        )

    if problemes_trouves:
        pytest.fail(
            "Moteurs de monnaie de depart incorrects :\n- "
            + "\n- ".join(problemes_trouves),
            pytrace=False,
        )

# Le moteur de monnaie attendu pour les lieux de dev dont les tests dependent
# (spec 15 §4.2 et §7, spec 14 §2). `festival` joue le role du reseau CLAF.
# / Expected engine of the dev venues tests rely on. `festival` plays the CLAF network.
MOTEURS_ATTENDUS_DES_LIEUX_DE_DEV = {
    "lespass": "v2",
    "le-coeur-en-or": "v2",
    "festival": "legacy",
}


def verifier_les_moteurs_de_depart():
    """
    Echoue, avec la consigne a suivre, si la base de dev n'a pas les moteurs de monnaie
    attendus par les tests qui en dependent.
    / Fails, with what to do, if the dev database lacks the expected currency engines.

    LOCALISATION : tests/outils_moteur_de_monnaie.py

    Ce qui est verifie :
    - `lespass` et `le-coeur-en-or` sont `v2`, `festival` est `legacy` ;
    - aucune ligne `Client` `test_*` n'est `legacy`. Un schema `test_*` cree avant la
      migration `Customers 0006` garde sa ligne `Client` en `legacy` : les tests de
      caisse V2, de kiosk et de tireuse tomberaient sur le verrou.

    Elle n'est PAS appliquee a toute la suite (seule `verifier_le_depart_de_la_suite()`
    l'est) : les tests qui en dependent demandent la fixture `moteurs_de_depart_verifies`
    de leur conftest.
    Jamais de `skip` : un etat faux doit se voir.
    / Not applied to the whole suite: only tests that rely on it ask for the fixture.
    """
    from Customers.models import Client

    problemes_trouves = []

    for nom_du_schema, moteur_attendu in MOTEURS_ATTENDUS_DES_LIEUX_DE_DEV.items():
        lieu = Client.objects.filter(schema_name=nom_du_schema).first()
        if lieu is None:
            problemes_trouves.append(
                f"le lieu `{nom_du_schema}` n'existe pas (relancer la demo : demo_data_v2)"
            )
            continue
        if lieu.moteur_monnaie != moteur_attendu:
            problemes_trouves.append(
                f"le lieu `{nom_du_schema}` est `{lieu.moteur_monnaie}`, "
                f"`{moteur_attendu}` attendu (verifier la migration BaseBillet 0227 "
                f"et la demo demo_data_v2)"
            )

    noms_des_lieux_de_test_en_legacy = list(
        Client.objects.filter(
            schema_name__startswith="test_",
            moteur_monnaie=Client.MOTEUR_LEGACY,
        ).values_list("schema_name", flat=True)
    )
    if noms_des_lieux_de_test_en_legacy:
        problemes_trouves.append(
            f"{len(noms_des_lieux_de_test_en_legacy)} lieu(x) `test_*` en `legacy` "
            f"({', '.join(sorted(noms_des_lieux_de_test_en_legacy))}) : "
            f"{CONSIGNE_POUR_LES_LIEUX_DE_TEST_EN_LEGACY}"
        )

    if problemes_trouves:
        pytest.fail(
            "Moteurs de monnaie de depart incorrects :\n- "
            + "\n- ".join(problemes_trouves),
            pytrace=False,
        )
