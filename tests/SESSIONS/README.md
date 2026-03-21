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
| 07 | Convertir PW reste → Fast | D | ~45 min | 02 | FAIT (2026-03-21) — 16 tests, 178 total |
| 08a | PW Live — batch leger (validations, crowds, CSS) | D | ~30 min | 04 | FAIT (2026-03-21) — 12 tests, 14 E2E total |
| 08b | PW Live — POS paiement + adhesion NFC | D | ~30 min | 08a | FAIT (2026-03-21) — 16 tests, 30 E2E total |
| 08c | PW Live — federation cross-tenant | D | ~15 min | 08a | FAIT (2026-03-21) — 1 test, 31 E2E total |
| 09a | Stripe mock — infra + 5 adhesions simples | D | ~30 min | 08c | FAIT (2026-03-21) — 5 tests, 183 pytest total |
| 09b | Stripe mock — adhesions complexes + crowds | D | ~20 min | 09a | FAIT (2026-03-21) — 8 tests, 191 pytest total |
| 09c | Stripe mock — reservations + 2 smoke E2E | D | ~30 min | 09a | FAIT (2026-03-21) — 4+2 tests, 228 total |
| 10 | Nettoyage final | E | ~15 min | 09a-c | FAIT (2026-03-21) — 228 tests, playwright/ supprime |
| 11 | Theme et langue (PW 99 oublie) | D | ~5 min | 10 | FAIT (2026-03-21) — 3 tests, 231 total |

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
              └──→ 04 → 08a → 08b (POS)
                         └──→ 08c (cross-tenant)
                         └──→ 09a → 09b (adhesions complexes)
                                └──→ 09c (reservations + smoke)
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
