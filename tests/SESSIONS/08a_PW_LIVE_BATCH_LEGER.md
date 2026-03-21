# Session 08a — Convertir PW TS → Playwright Python (batch leger)

## Statut : FAIT (2026-03-21)

## Objectif

Convertir 4 fichiers PW TS simples (sans POS NFC/setup lourd) en Playwright Python.
Valider l'infra E2E (conftest.py enrichi) avant les tests complexes.

## Ce qui a ete fait

### conftest.py enrichi (+6 fixtures)

| Fixture | Scope | Role |
|---|---|---|
| `api_key` | session | Recupere la cle API via manage.py test_api_key |
| `django_shell` | session | Factory (python_code) → stdout. Shell Django tenant lespass |
| `create_event` | session | Factory POST /api/v2/events/ via requests |
| `create_product` | session | Factory POST /api/v2/products/ via requests |
| `setup_test_data` | session | Factory pour tests/scripts/setup_test_data.py |
| `pos_page` | function | Factory (page, pv_name) → page POS prete |

**Dual-mode container/host** : toutes les fixtures detectent si on est dans le container
(`shutil.which("docker") is None`) et adaptent les commandes (docker exec vs direct).

### 4 fichiers crees

| Fichier | Tests | Source TS | Resultat |
|---|---|---|---|
| `test_membership_validations.py` | 1 | PW 20 | PASS |
| `test_reservation_validations.py` | 1 | PW 18 | PASS |
| `test_crowds_participation.py` | 1 | PW 23 | PASS |
| `test_pos_tiles_visual.py` | 9 | PW 45 | 7 PASS + 2 SKIP |

### Resultats

- **14 tests E2E** (2 existants login + 12 nouveaux)
- **12 passed, 2 skipped** (Biere/Coca — donnees create_test_pos_data absentes)
- **178 tests pytest inchanges**
- Pattern `pos_page` valide et reutilisable pour 08b

### Point d'attention : template membership

Le TS original (PW 20) ciblait des selecteurs qui ne matchaient pas le vrai template.
La page `/memberships/` rend un modal Bootstrap (modal_form.html) sans data-testid.
La conversion cible `/memberships/<uuid>/` qui rend form.html (avec tous les data-testid).

## Verification

```bash
docker exec lespass_django poetry run pytest tests/e2e/ -v --tb=short
# 12 passed, 2 skipped

docker exec lespass_django poetry run pytest tests/pytest/ --co -q | tail -1
# 178 tests collected
```
