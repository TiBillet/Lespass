# Session 02 — Prototype FastTenantTestCase avec pytest

## Objectif

Convertir 1 test existant (`test_paiement_especes_cb.py`) pour utiliser `FastTenantTestCase` + `self.client` au lieu de `requests` HTTP. Valider que ROLLBACK fonctionne, que `--reuse-db` accelere, et mesurer le gain de temps.

## Pre-requis

- Session 01 terminee (pytest-django installe et configure)
- Conteneur `lespass_django` tourne

## Prompt a envoyer

```
Convertis le test tests/pytest/test_paiement_especes_cb.py pour utiliser FastTenantTestCase.

Contexte :
- pytest-django est installe (session 01)
- Le test actuel utilise probablement requests HTTP ou l'ORM directement
- Voir tests/PLAN_TEST.md section 5.1 pour le pattern cible
- Voir tests/django_test/test_sales_api.py pour un exemple existant qui utilise l'ORM

A faire :
1. Lire test_paiement_especes_cb.py pour comprendre ce qu'il teste
2. Creer une version qui utilise FastTenantTestCase + TenantClient + self.client
3. Le test doit rester dans tests/pytest/ (pas de nouveau dossier)
4. Verifier que les tests passent : docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v
5. Verifier que ROLLBACK fonctionne : lancer 2 fois, le 2e run ne doit pas voir les donnees du 1er
6. Mesurer le temps : comparer avec le temps avant conversion
```

## Verification

```bash
# 1. Le test passe
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v --tb=long

# 2. ROLLBACK fonctionne (2 runs identiques)
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v
# Les 2 runs doivent passer — pas de "unique constraint violated" ou residus

# 3. --reuse-db accelere
time docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py --reuse-db -v

# 4. Tous les autres tests passent toujours
docker exec lespass_django poetry run pytest tests/pytest/ -v --tb=short
```

## Critere de succes

- [ ] `test_paiement_especes_cb.py` utilise `FastTenantTestCase` + `self.client`
- [ ] Plus de `requests` HTTP dans ce fichier
- [ ] Les N tests du fichier passent
- [ ] 2 runs successifs passent (ROLLBACK OK)
- [ ] Les 27 autres fichiers pytest ne sont pas casses
- [ ] Temps du fichier < 5s (vs potentiellement 15-30s avant avec HTTP)

## Duree estimee

~30 minutes (lecture + conversion + debug).

## Risques

- **FastTenantTestCase + pytest** : django-tenants documente `FastTenantTestCase` pour `manage.py test`. Ca devrait marcher avec pytest-django mais c'est exactement ce qu'on valide ici.
- **Schema tenant** : `FastTenantTestCase` cree un schema `test_*` temporaire. Si le test a besoin de donnees specifiques (Products, PointDeVente...), il faut les creer dans `setUp`.
- **Si ca ne marche pas** : fallback sur `TenantTestCase` (plus lent, cree un vrai schema). Documenter le probleme.
