"""
La clé d'empreinte du lieu se lit et s'écrit en base, jamais dans le cache.
/ The venue's fingerprint key is read and written in the database, never in the cache.

LOCALISATION : tests/pytest/test_cle_d_empreinte_du_lieu.py

RÈGLE MÉTIER TESTÉE
Chaque vente réglée est scellée par une empreinte (HMAC) calculée avec la clé du lieu.
Cette clé vit dans `LaboutikConfiguration.hmac_key` (chiffrée Fernet). Le singleton est
mis en cache par django-solo (memcached, 5 minutes). Le cache peut garder un objet que
la base n'a pas : par exemple un objet créé dans une transaction annulée ensuite.
- `get_hmac_key()` et `get_or_create_hmac_key()` relisent la clé en base, jamais
  l'attribut de l'objet venu du cache : la clé de la base gagne toujours ;
- si la ligne du singleton ou sa clé manque en base, `get_or_create_hmac_key()` les
  écrit en base, sans lever d'erreur, puis vide le cache du singleton ;
- la migration de données `laboutik/migrations/0016_cle_d_empreinte_toujours_en_base`
  crée la ligne du singleton et sa clé dans chaque lieu ; rappelée, elle ne change pas
  une clé existante.
/ Both key readers read the database; a missing row or key is written in the
database; the data migration creates the row and the key, and never changes an
existing key.

CONTRAT SUPPOSÉ (ce que ces tests attendent du code)
- la migration `laboutik/migrations/0016_cle_d_empreinte_toujours_en_base.py` expose la
  fonction `creer_la_configuration_et_sa_cle(apps, schema_editor)` ; elle lit le modèle
  par `apps.get_model("laboutik", "LaboutikConfiguration")`, ne se sert pas de
  `schema_editor`, et ne fait rien dans le schéma public ;
- une clé est 32 octets en hexadécimal (64 caractères), chiffrée Fernet en base.
/ Assumed contract: the migration module and function name; a key is 64 hex chars.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin
(tests/PIEGES.md 13.1), la ligne du singleton et sa clé reviennent telles quelles en
base. Le cache, lui, n'est PAS annulé : il est partagé avec le serveur de dev
(tests/PIEGES.md 13.22). La fixture vide donc le cache du singleton avant et après
chaque test : le prochain `get_solo()` relit la base.
/ Rolled back per test; the shared cache is not, so the fixture clears the singleton's
cache before and after each test.

Spécification : brief TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-briefs/05-H-1-ter.md
(point 8, tests 10 à 12) ; tests/PIEGES.md 9.86.

Lancer / Run : make test ARGS="tests/pytest/test_cle_d_empreinte_du_lieu.py"
"""

import copy
import importlib
import string
from types import SimpleNamespace

import pytest
from django.apps import apps as registre_des_applications
from django_tenants.utils import tenant_context

from laboutik.models import LaboutikConfiguration
from root_billet.utils import fernet_decrypt, fernet_encrypt

pytestmark = pytest.mark.django_db

# Le module de la migration de données (son nom commence par un chiffre : on
# l'importe par son chemin en texte).
# / The data migration module (its name starts with a digit: imported by its path).
CHEMIN_DE_LA_MIGRATION = "laboutik.migrations.0016_cle_d_empreinte_toujours_en_base"

# Deux clés connues, pour savoir laquelle est rendue.
# / Two known keys, to tell which one is returned.
CLE_DU_CACHE = "1" * 64
CLE_DE_LA_BASE = "2" * 64


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`. Le cache du singleton est vidé avant et après le test : le
    cache n'est pas annulé avec la transaction, et le serveur de dev le lit aussi.
    / The `lespass` venue; the singleton cache is cleared before and after the test.
    """
    with tenant_context(tenant):
        LaboutikConfiguration.clear_cache()
        try:
            yield SimpleNamespace(tenant=tenant)
        finally:
            LaboutikConfiguration.clear_cache()


def poser_dans_le_cache_une_copie_de_la_configuration(cle_en_clair):
    """
    Met dans le cache une copie de la configuration du lieu, avec cette clé (ou sans
    clé si `cle_en_clair` est None). La base n'est pas touchée.
    / Puts in the cache a copy of the configuration, with this key (or none).
    """
    configuration_lue_en_base = LaboutikConfiguration.objects.get(
        pk=LaboutikConfiguration.singleton_instance_id
    )
    copie_pour_le_cache = copy.copy(configuration_lue_en_base)
    copie_pour_le_cache.set_hmac_key(cle_en_clair)
    copie_pour_le_cache.set_to_cache()


def cle_en_clair_lue_en_base():
    """
    La clé du lieu relue en base et déchiffrée, ou None si la ligne ou la clé manque.
    / The venue key read back from the database and decrypted, or None.
    """
    configuration_lue_en_base = LaboutikConfiguration.objects.filter(
        pk=LaboutikConfiguration.singleton_instance_id
    ).first()
    if configuration_lue_en_base is None:
        return None
    if not configuration_lue_en_base.hmac_key:
        return None
    return fernet_decrypt(configuration_lue_en_base.hmac_key)


def est_une_cle_de_64_caracteres_hexadecimaux(cle):
    """Dit si la clé fait 64 caractères hexadécimaux (32 octets).
    / Tells whether the key is 64 hex chars."""
    if cle is None or len(cle) != 64:
        return False
    for caractere in cle:
        if caractere not in string.hexdigits:
            return False
    return True


# --------------------------------------------------------------------------
# 10 — Le cache garde un objet sans clé, la base n'a pas la ligne
# / 10 — The cache keeps a keyless object, the database has no row
# --------------------------------------------------------------------------


def test_cle_lue_en_base_quand_le_cache_garde_un_objet_sans_ligne(lieu):
    """
    La ligne du singleton est supprimée en base. Le cache garde un objet sans clé,
    comme après une première création dans une transaction annulée.
    `get_or_create_hmac_key()` ne lève rien : la ligne et la clé sont écrites en base,
    la clé rendue est celle relue en base. Un second appel (même par l'objet du cache)
    rend la même clé.
    / The singleton row is deleted, the cache keeps a keyless object: the key is
    written in the database without error, and read back identical.
    """
    poser_dans_le_cache_une_copie_de_la_configuration(cle_en_clair=None)
    LaboutikConfiguration.objects.filter(
        pk=LaboutikConfiguration.singleton_instance_id
    ).delete()
    objet_venu_du_cache = LaboutikConfiguration.get_solo()
    assert objet_venu_du_cache.hmac_key is None

    cle_rendue = objet_venu_du_cache.get_or_create_hmac_key()

    assert est_une_cle_de_64_caracteres_hexadecimaux(cle_rendue)
    assert cle_en_clair_lue_en_base() == cle_rendue
    assert objet_venu_du_cache.get_or_create_hmac_key() == cle_rendue
    assert LaboutikConfiguration.get_solo().get_hmac_key() == cle_rendue


# --------------------------------------------------------------------------
# 11 — Le cache porte une clé, la base une autre : la base gagne
# / 11 — The cache holds a key, the database another one: the database wins
# --------------------------------------------------------------------------


def test_cle_de_la_base_gagne_sur_celle_du_cache(lieu):
    """
    Le cache porte un objet avec la clé K1, la base porte la clé K2.
    `get_hmac_key()` et `get_or_create_hmac_key()`, appelées sur l'objet du cache,
    rendent K2 : une empreinte n'est jamais calculée avec une clé que la base n'a pas.
    La clé de la base ne change pas.
    / Cache holds K1, database holds K2: both readers return K2; the database key
    does not change.
    """
    LaboutikConfiguration.objects.filter(
        pk=LaboutikConfiguration.singleton_instance_id
    ).update(hmac_key=fernet_encrypt(CLE_DE_LA_BASE))
    poser_dans_le_cache_une_copie_de_la_configuration(cle_en_clair=CLE_DU_CACHE)
    objet_venu_du_cache = LaboutikConfiguration.get_solo()
    assert fernet_decrypt(objet_venu_du_cache.hmac_key) == CLE_DU_CACHE

    cle_lue = objet_venu_du_cache.get_hmac_key()
    cle_lue_ou_creee = objet_venu_du_cache.get_or_create_hmac_key()

    assert cle_lue == CLE_DE_LA_BASE
    assert cle_lue_ou_creee == CLE_DE_LA_BASE
    assert cle_en_clair_lue_en_base() == CLE_DE_LA_BASE


# --------------------------------------------------------------------------
# 12 — La migration de données crée la ligne et sa clé, sans toucher une clé existante
# / 12 — The data migration creates the row and its key, never an existing key
# --------------------------------------------------------------------------


def test_migration_cree_la_configuration_et_sa_cle(lieu):
    """
    La fonction de la migration 0016, appelée dans le lieu :
    - sans ligne du singleton : elle crée la ligne et une clé de 64 caractères
      hexadécimaux ;
    - sur une ligne sans clé : elle crée une clé ;
    - rappelée sur une ligne qui a une clé : la clé ne change pas (même texte chiffré
      en base).
    / The migration function creates the row and a key, creates a key on a keyless
    row, and never changes an existing key.
    """
    module_de_la_migration = importlib.import_module(CHEMIN_DE_LA_MIGRATION)
    creer_la_configuration_et_sa_cle = (
        module_de_la_migration.creer_la_configuration_et_sa_cle
    )
    lignes_du_singleton = LaboutikConfiguration.objects.filter(
        pk=LaboutikConfiguration.singleton_instance_id
    )

    # Sans ligne / Without a row
    lignes_du_singleton.delete()
    creer_la_configuration_et_sa_cle(registre_des_applications, None)
    assert lignes_du_singleton.exists()
    assert est_une_cle_de_64_caracteres_hexadecimaux(cle_en_clair_lue_en_base())

    # Ligne sans clé / Row without a key
    lignes_du_singleton.update(hmac_key=None)
    creer_la_configuration_et_sa_cle(registre_des_applications, None)
    assert est_une_cle_de_64_caracteres_hexadecimaux(cle_en_clair_lue_en_base())

    # Rappelée : la clé existante ne change pas / Called again: the key stays
    texte_chiffre_avant = lignes_du_singleton.get().hmac_key
    creer_la_configuration_et_sa_cle(registre_des_applications, None)
    assert lignes_du_singleton.get().hmac_key == texte_chiffre_avant
