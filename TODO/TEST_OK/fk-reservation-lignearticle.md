# FK reservation sur LigneArticle

## Ce qui a ete fait

Ajout d'une FK directe `LigneArticle.reservation` pour lier une ligne comptable
a sa reservation sans passer par `Paiement_stripe` comme intermediaire.

### Pourquoi

Avant, le seul lien entre Reservation et LigneArticle passait par :
`Reservation → Paiement_stripe ← LigneArticle`

Les reservations admin (cheque, especes) n'ont pas de `Paiement_stripe` :
leurs LigneArticle etaient **orphelines**, impossibles a retrouver.
Ca causait un bug : annuler une reservation admin ne creait aucune trace comptable.

Avec la FK directe : `Reservation ← LigneArticle.reservation`
— le lien est garanti par l'integrite referentielle, quel que soit le moyen de paiement.

### Modifications

| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | FK `reservation` sur LigneArticle (nullable, PROTECT) |
| `BaseBillet/validators.py:290` | `reservation=reservation` sur LigneArticle.objects.create (front Lespass) |
| `ApiBillet/serializers.py:1175` | `reservation=reservation` (API v1) |
| `api_v2/serializers.py:1118` | `reservation=reservation` + suppression hack metadata UUID (API v2 free) |
| `Administration/admin_tenant.py:3379` | `reservation=reservation` (admin direct) |
| `BaseBillet/models.py` | `articles_paid()` simplifie avec FK directe + fallback legacy |
| `BaseBillet/models.py` | `_lignes_hors_stripe()` simplifie avec FK directe + fallback legacy |
| Migration 0200 | Ajout du champ FK |
| Migration 0201 | Backfill : renseigne `reservation` depuis `paiement_stripe.reservation` pour les lignes existantes |

### Compatibilite

- **Fallback integre** : `articles_paid()` et `_lignes_hors_stripe()` tentent d'abord la FK directe,
  puis retombent sur l'ancien chemin via `paiement_stripe` si la FK n'est pas renseignee.
- **Les anciennes lignes** sont backfillees automatiquement par la migration 0201.
- **Paiement_stripe inchange** : les FK existantes et le flow Stripe ne sont pas touches.

### Vision future

Cette FK est la premiere etape pour decouplage de Stripe :
- A terme, `Paiement_stripe` pourra etre generalise (PayPal, Stancer, etc.)
  ou remplace par un modele `Payment` generique
- Le lien `LigneArticle → Reservation` restera stable quel que soit le fournisseur de paiement

---

## Tests a realiser

### Test 1 : Nouvelle reservation admin → FK renseignee

```
1. Admin → Evenements → choisir un evenement
2. Creer une reservation via l'admin (moyen de paiement : Especes)
3. Verifier en base :
   docker exec lespass_django poetry run python manage.py shell -c "
   from BaseBillet.models import LigneArticle
   for l in LigneArticle.objects.filter(sale_origin='AD').order_by('-datetime')[:3]:
       print(l.uuid, l.reservation_id, l.paiement_stripe_id)
   "
4. La LigneArticle doit avoir reservation_id renseigne (pas null)
```

### Test 2 : Reservation Stripe (front) → FK renseignee

```
1. Aller sur le site public, reserver un billet (carte test 4242...)
2. Verifier en base : la LigneArticle a reservation_id renseigne
3. Elle a aussi paiement_stripe renseigne (les deux coexistent)
```

### Test 3 : Annulation reservation admin → avoir cree

```
1. Creer une reservation admin (especes)
2. Annuler la reservation (admin → bouton Annuler)
3. Verifier : un avoir CREDIT_NOTE est cree, lie a la reservation via FK directe
```

### Test 4 : Annulation reservation Stripe → remboursement Stripe inchange

```
1. Creer une reservation Stripe (carte test)
2. Annuler depuis l'admin ou depuis "mon compte"
3. Verifier :
   - Le remboursement Stripe est effectue (ligne REFUNDED)
   - Pas d'avoir CREDIT_NOTE supplementaire
   - Le flow est identique a avant
```

### Test 5 : Backfill des anciennes lignes

```
Verifier que les lignes existantes ont ete backfillees :
docker exec lespass_django poetry run python manage.py shell -c "
from BaseBillet.models import LigneArticle
total = LigneArticle.objects.filter(paiement_stripe__reservation__isnull=False).count()
filled = LigneArticle.objects.filter(reservation__isnull=False).count()
print(f'Lignes avec paiement_stripe.reservation: {total}')
print(f'Lignes avec reservation FK directe: {filled}')
"
Les deux nombres doivent etre egaux (ou proches).
```

### Test 6 : API v2 free booking → FK renseignee

```
curl -X POST https://lespass.tibillet.localhost/api/v2/events/{uuid}/reservations/ \
  -H "Authorization: Api-Key <KEY>" \
  -H "Content-Type: application/json" \
  -d '{"prices": [{"uuid": "<price_uuid>", "qty": 1}]}'

Verifier en base : la LigneArticle creee a reservation_id renseigne.
Le champ metadata ne contient plus "reservation_uuid" (supprime, remplace par la FK).
```
