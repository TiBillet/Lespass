# Webhook Stripe `invoice.paid` : un abonnement hors TiBillet ne lève plus de 500 / Stripe `invoice.paid`: a non-TiBillet subscription no longer raises a 500

**Date :** 2026-09-17
**Migration :** Non
**Sentry :** BILLETTERIE-COOP-TD, BILLETTERIE-COOP-TE, BILLETTERIE-COOP-TB

## Resume / Summary

**Quoi / What :** un renouvellement Stripe (`invoice.paid`,
`billing_reason=subscription_cycle`) sans metadata TiBillet est maintenant ignoré
proprement : `logger.error` (alerte Sentry) et réponse **204**. Avant, `metadata['tenant']`
levait une `KeyError`, d'où une 500 et des tentatives répétées par Stripe.
/ A Stripe renewal without TiBillet metadata is now skipped with an error log and a 204
instead of a KeyError / 500.

**Pourquoi / Why :** avec **Stripe Connect, la plateforme reçoit les webhooks de TOUS les
comptes connectés**, y compris pour des objets que Lespass n'a jamais créés. Un lieu qui
crée un abonnement directement dans son dashboard Stripe produit des `invoice.paid` reçus
par TiBillet à chaque cycle, sans les metadata posées au checkout (`tenant`,
`membership_uuid`, `price_uuid`). Le handler `checkout.session.completed` avait déjà cette
garde ; `invoice.paid` a maintenant la même.
/ With Stripe Connect, the platform receives webhooks from every connected account,
including subscriptions created outside Lespass.

Deux choix volontaires :
- **`logger.error` et non `warning`** : la `LoggingIntegration` Sentry a
  `event_level=ERROR` par défaut, un `warning` resterait invisible. On veut une alerte
  pour aller vérifier l'abonnement côté Stripe. L'`id` de l'abonnement est dans le
  message : Sentry groupe par abonnement.
- **Réponse 204 et non 500** : Stripe acquitte et cesse de réessayer.

**Piège encore ouvert / Known trap :** sur le schéma **public**, toute 500 déclenche aussi
un `NoReverseMatch: 'staff_admin'`. Le handler `mail_admins` rend `technical_500.txt`, qui
fait un `repr()` de chaque setting : les `reverse_lazy("staff_admin:…")` de
`UNFOLD["TABS"]` échouent, car `urls_public.py` ne déclare pas ce namespace.
/ Any 500 on the public schema still cascades into a `NoReverseMatch: 'staff_admin'`.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | `Webhook_stripe.post`, branche `invoice.paid` : garde `if not metadata.get('tenant')` → `logger.error` + `204 NO_CONTENT` |
| `tests/pytest/test_webhook_invoice_paid_sans_metadata.py` | Nouveau — 2 tests : réponse 204, log ERROR qui cite l'abonnement |

---

## Comment tester (a la main) / Manual test

### Test 1 — abonnement créé hors Lespass
1. Dans le dashboard Stripe (mode test) d'un compte connecté, créer un abonnement
   directement (sans passer par Lespass).
2. `stripe listen --forward-to https://<tenant>/api/webhook_stripe/` puis
   `stripe trigger invoice.paid` sur ce compte, ou avancer l'horloge de test de
   l'abonnement d'un cycle.
3. **Attendu :** réponse **204** dans `stripe listen`, une ligne d'erreur dans les logs
   Django avec l'`id` de l'abonnement, aucune 500, aucune nouvelle tentative de Stripe.

### Test 2 — abonnement Lespass (non-régression)
1. Prendre une adhésion récurrente via Lespass, puis déclencher un cycle de
   renouvellement.
2. **Attendu :** l'adhésion est renouvelée comme avant.

### Tests automatisés
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_webhook_invoice_paid_sans_metadata.py -q
```
