# Sessions de migration des tests

Chaque fichier est une fiche de session autonome avec :
- L'objectif
- Le prompt exact a envoyer a Claude Code
- Les commandes de verification
- Les criteres de succes

## Vue d'ensemble

| # | Session | Phase | Duree | Depend de | Statut |
|---|---------|-------|-------|-----------|--------|
| 01 | Installer pytest-django | B | ~15 min | — | FAIT (2026-03-20) |
| 02 | Prototype FastTenantTestCase | B | ~30 min | 01 | FAIT (2026-03-20) |
| 03 | Convertir 15 tests API v2 | D | ~45 min | 02 | FAIT (2026-03-20) |
| 04 | Prototype Playwright Python E2E | C | ~20 min | 01-02 | FAIT (2026-03-20) — serveur externe (pas LiveServer), fixtures pytest |
| 05 | Convertir PW admin → Fast | D | ~1h | 02 | FAIT (2026-03-20) — 20 tests, 142 total |
| 06 | Convertir PW adhesions → Fast | D | ~1h30 | 02 | FAIT (2026-03-20) — 20 tests, 162 total |
| 07 | Convertir PW reste → Fast | D | ~45 min | 02 |  |
| 08 | Convertir PW → PlaywrightLive | D | ~1h30 | 04 |  |
| 09 | Convertir PW Stripe → PlaywrightLive | D | ~2h | 04 |  |
| 10 | Nettoyage final | E | ~30 min | 01-09 |  |

## Temps total estime

~9h de travail Claude Code, reparties sur **5-7 sessions humaines** (on peut regrouper).

## Regroupements suggeres

| Jour | Sessions | Duree |
|------|----------|-------|
| Jour 1 | 01 + 02 | ~45 min |
| Jour 2 | 03 + 04 | ~1h30 |
| Jour 3 | 05 + 06 | ~2h30 |
| Jour 4 | 07 + 08 | ~2h15 |
| Jour 5 | 09 + 10 | ~2h30 |

## Ordre des sessions

```
01 ──→ 02 ──→ 03 (API v2)
              ├──→ 05 → 06 → 07 (FastTenantTestCase)
              └──→ 04 → 08 → 09 (PlaywrightLive)
                                  └──→ 10 (nettoyage)
```

Les branches 03, 05-07 et 04/08-09 sont **independantes** apres session 02. On peut les faire dans n'importe quel ordre. La seule contrainte : 04 avant 08-09.

## Comment utiliser

1. Ouvrir la fiche de la prochaine session
2. Copier le prompt dans Claude Code
3. Laisser Claude travailler
4. Executer les commandes de verification
5. Cocher les criteres de succes
6. Passer a la session suivante
