# Session 03 — Convertir les 15 tests API v2 (requests → self.client)

## Objectif

Migrer les 15 fichiers `test_event_*.py`, `test_postal_address_*.py`, `test_reservation_*.py`, `test_membership_*.py`, `test_crowd_*.py` : remplacer `requests.get/post` par `self.client.get/post` (in-process). Garder pytest, changer le transport.

## Pre-requis

- Session 02 terminee (FastTenantTestCase valide avec pytest)
- Le pattern de conversion est connu et fonctionne

## Prompt a envoyer

```
Convertis les 15 tests API v2 dans tests/pytest/ pour utiliser self.client au lieu de requests HTTP.

Contexte :
- Session 02 a valide que FastTenantTestCase fonctionne avec pytest
- Les 15 fichiers sont : test_event_create.py, test_events_list.py, test_event_retrieve.py, test_event_delete.py, test_event_create_extended.py, test_event_images.py, test_event_link_address.py, test_postal_address_crud.py, test_postal_address_images.py, test_reservation_create.py, test_membership_create.py, test_crowd_initiative_create.py, test_crowd_initiative_list.py, test_crowd_budget_item_flow.py, test_crowd_votes_participations.py
- Voir tests/PLAN_TEST.md section 3.1

Pattern de conversion :
- Remplacer `requests.get(url, headers=...)` par `self.client.get(path, HTTP_AUTHORIZATION=...)`
- Remplacer `requests.post(url, json=data)` par `self.client.post(path, data, content_type='application/json')`
- Remplacer `response.json()` par `response.json()`  (meme API sur Django test client)
- Remplacer `response.status_code` par `response.status_code` (identique)
- URL : passer de `https://lespass.tibillet.localhost/api/v2/events/` a `/api/v2/events/`

Fais les 15 fichiers. Verifie apres chaque fichier que le test passe.
```

## Verification

```bash
# Tous les tests API v2 passent
docker exec lespass_django poetry run pytest tests/pytest/test_event*.py tests/pytest/test_postal*.py tests/pytest/test_reservation*.py tests/pytest/test_membership*.py tests/pytest/test_crowd*.py -v --tb=short

# Tous les tests passent (regression)
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short --reuse-db

# Plus de 'import requests' dans les fichiers API v2
grep -l "import requests" tests/pytest/test_event*.py tests/pytest/test_postal*.py tests/pytest/test_reservation*.py tests/pytest/test_membership*.py tests/pytest/test_crowd*.py
# Doit retourner vide
```

## Critere de succes

- [ ] 15 fichiers convertis
- [ ] 0 `import requests` dans ces fichiers
- [ ] Tous les tests passent
- [ ] Temps total des 15 fichiers < 10s (vs ~45s avant avec HTTP)

## Duree estimee

~45 minutes (conversion mecanique x15, mais chaque fichier est petit).

## Risques

- **Headers d'auth** : `self.client` utilise `HTTP_AUTHORIZATION='Api-Key xxx'` (prefixe `HTTP_`). Piege classique.
- **Content-Type** : `self.client.post` ne met pas `application/json` par defaut. Toujours passer `content_type='application/json'`.
- **URLs absolues vs relatives** : les tests actuels utilisent probablement des URLs absolues avec le domaine. Il faut les convertir en chemins relatifs (`/api/v2/...`).
- **conftest.py** : le fixture `_inject_cli_env` qui genere l'API key peut rester — il sera utilise differemment (via `self.client` au lieu de `requests`).
