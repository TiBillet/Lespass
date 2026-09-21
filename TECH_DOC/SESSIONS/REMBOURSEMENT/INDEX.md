# Remboursements billetterie — hub

> Remboursements Stripe et avoirs hors Stripe des réservations
> (`cancel_and_refund_resa`, `cancel_and_refund_ticket`, `partial_refund_payment`).

| Chantier | Fichier | Status |
|---|---|---|
| 01 | [`SPEC.md`](SPEC.md) — corrections (filtre `H`, avoirs d'autres clients, lignes de remboursement, avoirs billet par billet, garde-fou) + tests avec/sans panier + Stripe réel et `make` | Implémenté le 2026-09-21, relu par Fable (plan) et Opus (code) |

Contexte historique : `CHANGELOG/refund_refactor.md` (réécriture du 7 juillet, `partial_refund_payment`).
