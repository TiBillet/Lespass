# Issue #319 : remboursements et avoirs vers LaBoutik

## Ce qui a été fait
Un remboursement ou un avoir n'est plus perdu quand LaBoutik ne connaît pas la vente
d'origine : la tâche renvoie d'abord la vente, puis réessaie. Les deux avoirs qui
oubliaient l'uuid de la vente d'origine l'envoient maintenant.
Détails : `CHANGELOG/2026-10-01-issue-319-remboursements-laboutik.md`.

Prérequis pour tous les tests : un tenant relié à un serveur LaBoutik (cashless) de test,
et les logs du worker Celery ouverts.

## Tests à réaliser

### Test 1 : remboursement d'une vente déjà dans LaBoutik (cas normal)
1. Acheter un billet en ligne (carte Stripe de test `4242 4242 4242 4242`).
2. Vérifier dans LaBoutik que la vente est arrivée.
3. Dans l'admin, rembourser le billet.
4. La ligne négative arrive dans LaBoutik. Dans l'admin Lespass, la ligne de
   remboursement est marquée « Sended to LaBoutik ».

### Test 2 : remboursement d'une vente jamais arrivée dans LaBoutik (le bug)
1. Couper le serveur LaBoutik (ou mettre une mauvaise URL cashless dans la configuration).
2. Acheter un billet en ligne. La vente n'arrive pas dans LaBoutik.
3. Remettre le serveur LaBoutik en route, puis forcer l'état « pas envoyée » :
   ```bash
   docker exec -it lespass_django poetry run python manage.py tenant_command shell --schema=<tenant>
   >>> from BaseBillet.models import LigneArticle
   >>> LigneArticle.objects.filter(uuid="<uuid de la vente>").update(sended_to_laboutik=False)
   ```
4. Rembourser le billet dans l'admin.
5. Logs Celery attendus : « vente d'origine … pas encore envoyee a LaBoutik -> on relance
   send_sale_to_laboutik », puis la vente part, puis le remboursement part après ~30 s.
6. Dans LaBoutik : la vente ET le remboursement sont présents.

### Test 3 : avoir depuis l'annulation d'une adhésion
1. Admin > Adhésions : choisir une adhésion payée en espèces.
2. Annuler l'adhésion en cochant « avec avoir ».
3. L'avoir arrive dans LaBoutik (plus d'erreur 400 dans les logs).
4. Vérifier en base que l'avoir porte l'uuid d'origine :
   ```bash
   >>> LigneArticle.objects.filter(status="N").latest("datetime").metadata
   # doit contenir 'original_lignearticle_uuid'
   ```

### Test 4 : action admin « Avoir » sur une ligne de vente
1. Admin > Ventes : sur une ligne payée, cliquer l'action « Avoir ».
2. L'avoir arrive dans LaBoutik (plus d'erreur 400 dans les logs).

### Test 5 : logs serveur injoignable
1. Couper le serveur LaBoutik, faire une vente.
2. Le log d'erreur donne : nom de la tâche, URL du serveur, tenant, numéro de tentative,
   et l'exception (au lieu de « Serveur down ? »).

### Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_send_refund_to_laboutik.py tests/pytest/test_admin_annulation_abonnement_stripe.py -v
```

## Compatibilité
- Pas de migration.
- Les lignes déjà abandonnées (remboursements et avoirs en 404/400 avant ce correctif)
  ne sont pas renvoyées automatiquement.
- Le message Sentry change : l'ancienne issue Sentry BILLETTERIE-COOP-F9 (« Serveur
  down ? ») ne se déclenchera plus. Les nouvelles erreurs auront leur propre titre.
- Côté LaBoutik, rien ne change : `RefundFromLespass` attend toujours
  `metadata.original_lignearticle_uuid`.
