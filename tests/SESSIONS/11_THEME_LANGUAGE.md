# Session 11 — Theme et langue (PW 99)

## Statut : FAIT (2026-03-21)

## Depend de : 10 (nettoyage)

## Objectif

Convertir le fichier oublie `99-theme_language.spec.ts` (3 tests theme/langue).

## Ce qui a ete fait

### 1 fichier cree

| Fichier | Tests | Source TS | Resultat |
|---|---|---|---|
| `tests/e2e/test_theme_language.py` | 3 | PW 99 | 3 PASS |

### Details des 3 tests

1. `test_toggle_theme` — clic `#themeToggle` → `data-bs-theme` bascule dark/light → re-clic retour
2. `test_switch_language` — dropdown `#languageDropdown` → clic `.language-select-btn[data-lang="en"]` → `html[lang]` change → page rechargee
3. `test_sync_theme_language_preferences` — login admin → `/my_account/profile/` → toggle `#darkThemeCheck` → select `#languageSelect` → verification synchronisation

### Resultats

- **36 E2E** (33 + 3)
- **195 pytest** inchanges
- **231 tests au total**

## Note

Ce fichier avait ete oublie lors de la migration sessions 01-10.
Decouvert en verifiant l'inventaire section 4 du PLAN_TEST.md (51 fichiers TS).
Le seul autre fichier non converti est `40-laboutik-commandes-tables.spec.ts` (7 tests),
intentionnellement SKIP car la feature "commandes tables" est incomplete.

## Verification

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_theme_language.py -v -s
# 3 passed
```
