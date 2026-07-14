"""
Tests des filtres de temps de l'API v2 Events : `only_futur` et `next_days`.
/ Time filters of the v2 Events API.

LOCALISATION : tests/pytest/test_api_v2_events_filtres_temps.py

CE QUE CES TESTS PROTEGENT
--------------------------
`GET /api/v2/events/?only_futur=1` renvoyait un **500 a tous les coups**. Le module
`datetime` etait importe (`import datetime`), mais le code appelait `datetime.now()` —
qui n'existe que sur la CLASSE `datetime.datetime`, pas sur le module. Chaque appel levait
`AttributeError: module 'datetime' has no attribute 'now'`.

Un second bug, latent, se cachait juste derriere : `now.replace(day=now.day - 1)` aurait
lance `ValueError: day is out of range` le **1er de chaque mois** (day - 1 = 0).

Ces tests sont des tests d'INTEGRATION : ils tapent l'API HTTP en boite noire, sur le
tenant de dev. Ils sont en LECTURE SEULE (que des GET) et ne creent rien.
/ Integration tests: black-box HTTP calls, read-only.
"""

import os

import pytest
import requests


def _url_des_events():
    base = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    return f"{base}/api/v2/events/"


def _entetes():
    cle_api = os.getenv("API_KEY")
    if not cle_api:
        pytest.skip("Pas de cle API dans l'environnement.")
    return {"Authorization": f"Api-Key {cle_api}"}


def _appeler(params=None):
    return requests.get(
        _url_des_events(), headers=_entetes(), params=params or {}, timeout=15, verify=False
    )


@pytest.mark.integration
class TestOnlyFutur:

    def test_only_futur_ne_renvoie_plus_500(self):
        """
        NON-REGRESSION. C'est LE test du bug : `datetime.now()` sur le MODULE datetime
        levait une AttributeError, et l'endpoint renvoyait 500 a chaque appel.
        """
        reponse = _appeler({"only_futur": "1"})
        assert reponse.status_code == 200, (
            f"only_futur renvoie HTTP {reponse.status_code} : {reponse.text[:300]}"
        )

    def test_only_futur_ne_renvoie_aucun_event_passe_et_termine(self):
        """
        Un event dont la date de debut ET la date de fin sont passees ne doit pas remonter.
        On tolere les events d'HIER (le filtre part de la veille) et les events EN COURS
        (commences avant, mais se terminant apres).
        """
        from datetime import datetime, timedelta, timezone as tz_utc

        reponse = _appeler({"only_futur": "1"})
        assert reponse.status_code == 200

        borne_basse = datetime.now(tz_utc.utc) - timedelta(days=2)  # marge d'un jour
        for event in reponse.json()["results"]:
            debut = datetime.fromisoformat(event["startDate"])
            fin = (
                datetime.fromisoformat(event["endDate"])
                if event.get("endDate")
                else None
            )
            evenement_encore_dactualite = debut >= borne_basse or (
                fin is not None and fin >= borne_basse
            )
            assert evenement_encore_dactualite, (
                f"'{event['name']}' est passe et termine, il ne devrait pas remonter."
            )

    def test_sans_filtre_on_recoit_au_moins_autant_devents(self):
        """only_futur RESTREINT : il ne peut pas renvoyer plus que la liste complete."""
        tous = _appeler().json()["results"]
        futurs = _appeler({"only_futur": "1"}).json()["results"]
        assert len(futurs) <= len(tous)


@pytest.mark.integration
class TestNextDays:

    def test_next_days_repond_200(self):
        reponse = _appeler({"next_days": "30"})
        assert reponse.status_code == 200, reponse.text[:300]

    def test_next_days_ne_renvoie_rien_au_dela_de_la_fenetre(self):
        """Un event qui commence dans 60 jours ne doit pas sortir avec next_days=30."""
        from datetime import datetime, timedelta, timezone as tz_utc

        reponse = _appeler({"next_days": "30"})
        assert reponse.status_code == 200

        borne_haute = datetime.now(tz_utc.utc) + timedelta(days=31)  # marge d'un jour
        for event in reponse.json()["results"]:
            debut = datetime.fromisoformat(event["startDate"])
            assert debut < borne_haute, (
                f"'{event['name']}' commence le {debut}, hors de la fenetre de 30 jours."
            )

    def test_une_fenetre_plus_large_ne_renvoie_jamais_moins_devenements(self):
        """
        ORACLE : next_days=365 est un sur-ensemble de next_days=7. Si ce n'est pas le cas,
        le filtre de fenetre est faux.
        """
        sur_7_jours = _appeler({"next_days": "7"}).json()["results"]
        sur_365_jours = _appeler({"next_days": "365"}).json()["results"]

        assert len(sur_365_jours) >= len(sur_7_jours)

        uuids_sur_7 = {e["identifier"] for e in sur_7_jours}
        uuids_sur_365 = {e["identifier"] for e in sur_365_jours}
        assert uuids_sur_7 <= uuids_sur_365, (
            "Des events de la fenetre de 7 jours manquent dans celle de 365 jours."
        )

    def test_next_days_lemporte_sur_only_futur(self):
        """
        Si les deux parametres sont fournis, next_days gagne (il est plus restrictif).
        On compare les ENSEMBLES d'uuid, pas les longueurs : deux listes de meme taille
        peuvent contenir des events differents.
        """
        avec_les_deux = _appeler({"only_futur": "1", "next_days": "7"}).json()["results"]
        avec_next_days_seul = _appeler({"next_days": "7"}).json()["results"]

        assert {e["identifier"] for e in avec_les_deux} == {
            e["identifier"] for e in avec_next_days_seul
        }


@pytest.mark.integration
class TestNextDaysValidation:

    def test_next_days_non_numerique_renvoie_400_et_pas_500(self):
        """Une valeur absurde doit donner une erreur CLIENT, pas un plantage serveur."""
        reponse = _appeler({"next_days": "trente"})
        assert reponse.status_code == 400, reponse.text[:200]

    def test_next_days_a_zero_renvoie_400(self):
        assert _appeler({"next_days": "0"}).status_code == 400

    def test_next_days_negatif_renvoie_400(self):
        assert _appeler({"next_days": "-5"}).status_code == 400

    def test_next_days_trop_grand_renvoie_400(self):
        """Au-dela d'un an, autant demander la liste complete."""
        assert _appeler({"next_days": "5000"}).status_code == 400
