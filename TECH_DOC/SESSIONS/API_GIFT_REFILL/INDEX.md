# API_GIFT_REFILL — Hub

Route API v2 de recharge de tokens « cadeau » (TNF) sur la tirelire d'un user,
authentifiée par clé API restreinte à un asset.

## Documents
- [SPEC.md](SPEC.md) — spécification validée (2026-05-21)
- PLAN.md — plan d'implémentation (à venir, skill writing-plans)

## En une phrase
`POST /api/v2/wallet-refills/` : `email` + `asset` (uuid TNF) + `amount` (int) →
crédite la tirelire via Fedow, si la clé API autorise cet asset cadeau.

## Décisions clés
- api_v2 · permission clé seule · FK `gift_asset` (TNF) sur ExternalApiKey =
  interrupteur + restriction · montant unité brute · plafond hardcodé 10000 ·
  idempotence par cache Redis (header `Idempotency-Key`).
