# kiosk : crédit de la carte par Lespass (base locale)

## Ce qui a été fait
Quand Stripe confirme le paiement, `PaymentsIntent.get_from_stripe()` appelle `kiosk/credit.py`, qui
crédite la carte dans `fedow_core` avec les fonctions de la caisse (`_executer_recharges`). Un seul
crédit par paiement (`carte_creditee_le`, verrou). Le solde de la borne = Fedow distant + base locale.
Détails : `CHANGELOG/2026-09-29-kiosk-credit-local.md`.

## Pré-requis
- `migrate_schemas kiosk` (migration 0005), puis **redémarrer le worker Celery**.
- Le lieu a une monnaie locale (Asset TLF) → produit « Recharge euros » avec un tarif « Libre ».

## Tests à réaliser

### Test 1 : recharge simulée créditée
1. DEMO=1. `/kiosk/` → poser une carte client (simulateur). Noter le solde.
2. Choisir 10 €, « Payer », puis « Simuler le paiement ».
3. Attendu : écran de succès avec nouveau solde = ancien + 10 €.
4. Revenir à l'accueil, reposer la même carte : le solde affiché a bien augmenté de 10 €.
5. Caisse LaBoutik : scanner la même carte → même solde en monnaie locale.

### Test 2 : pas de double crédit
1. Pendant l'attente du paiement, couper le worker Celery, puis cliquer « Simuler le paiement ».
2. Le sondage de secours (10 s) affiche le succès et crédite.
3. Relancer le worker. Vérifier que la carte n'est créditée qu'une fois (solde + 1 seule ligne de vente).

### Test 3 : refus
1. « Simuler un refus » puis « Annuler » → écran de refus, solde inchangé.

### Test 4 : admin
1. Admin → Kiosk → paiements : colonne « Carte créditée le » remplie pour les paiements réussis.

### Vérification en base
```bash
docker exec lespass_django poetry run python manage.py shell -c "
from django_tenants.utils import schema_context
from kiosk.models import PaymentsIntent
with schema_context('lespass'):
    for p in PaymentsIntent.objects.order_by('-datetime')[:5]:
        print(p.datetime, p.amount, p.status, p.carte_creditee_le, p.card)
"
```

### Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_kiosk_*.py -q
```

## Compatibilité
- Plus besoin du webhook Stripe → Fedow ni du patch Fedow (SPEC §8bis).
- Les lignes de vente apparaissent dans les rapports de caisse comme une recharge euros payée par
  « Carte bancaire (TPE) », origine « Caisse ».
