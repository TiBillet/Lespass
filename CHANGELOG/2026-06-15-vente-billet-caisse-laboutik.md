# Vente de billet en caisse LaBoutik → réservation Lespass (API v2)

**Date :** 2026-06-15
**Migration :** Non

## Ce qui a été fait

Origine : crash 500 en prod (cafeasso, 2026-06-11) — `AttributeError: 'Commande'
object has no attribute 'methode_BI'`. Les articles `BILLET` synchronisés depuis
Lespass étaient vendables en caisse mais sans handler, et aucune remontée du
billet vers Lespass n'existait.

Le flux est maintenant : vente en caisse (espèce ou CB) → appel synchrone
`POST /api/v2/reservations/` avec la clé `lespass_api_key` → Lespass déduit
l'évènement depuis le tarif, crée la réservation `VALID` + tickets `NOT_SCANNED`
+ `LigneArticle` `VALID` (`sale_origin=LABOUTIK`, `payment_method=CASH|CC`),
envoie le billet PDF par mail → la caisse enregistre l'`ArticleVendu` local avec
l'uuid de la réservation en metadata. Si Lespass refuse ou ne répond pas : la
vente est annulée (transaction atomique), rien n'est débité.

### Modifications

| Fichier | Changement |
|---|---|
| `BaseBillet/validators.py` (Lespass) | `TicketCreator` mode `paid_externally` : LigneArticle `VALID`, tickets `NOT_SCANNED`, pas de checkout Stripe |
| `api_v2/serializers.py` (Lespass) | `reservationFor` optionnel (résolution d'évènement depuis le tarif) + `additionalProperty paymentMethod` cash/card |
| `tests/pytest/test_api_v2_reservation_laboutik.py` (Lespass) | 5 tests pytest DB-only |
| `webview/billet_lespass.py` (LaBoutik) | Nouveau — appel API v2, timeout (3, 5), erreurs lisibles |
| `webview/views.py` (LaBoutik) | `Commande.methode_BI` — espèce/CB only, email carte NFC sinon config caisse |

## Prérequis de configuration

1. **Côté Lespass** : créer une `ExternalApiKey` (admin → API keys) avec la
   permission **Bookings (reservation)** cochée.
2. **Côté LaBoutik** : renseigner cette clé dans `Configuration.lespass_api_key`
   et vérifier `Configuration.billetterie_url` (doit finir par `/`, le `save()`
   l'assure) et `Configuration.email` (fallback billet anonyme).
3. Un produit Lespass de catégorie **Billet payant** lié à UN SEUL évènement
   publié à venir, synchronisé en caisse (l'article LaBoutik a pour pk l'uuid
   du tarif Lespass), placé sur un point de vente.

## Tests à réaliser

### Test 1 : vente espèce anonyme (nominal)
1. En caisse, vendre l'article billet, payer en espèces.
2. La vente passe (plus de crash 500), ticket de caisse normal.
3. Côté Lespass admin : une réservation `VALID` existe sur l'évènement,
   2 colonnes vérifiables : origine de vente "Cash register" (LB) et
   moyen de paiement "Cash".
4. L'email de la Configuration LaBoutik reçoit le billet PDF.

### Test 2 : vente CB avec carte NFC d'un membre connu
1. Scanner la carte d'un membre qui a un email, payer en CB.
2. Le billet arrive sur l'email du membre, la réservation est à son nom.

### Test 3 : évènement ambigu
1. Lier le produit billet à un 2e évènement publié à venir.
2. La vente est refusée avec un message clair (« Several upcoming events... »).
3. Rien n'est débité, aucun ArticleVendu créé.

### Test 4 : Lespass injoignable
1. Couper Lespass (ou mettre une mauvaise URL).
2. La vente est refusée : « Billetterie injoignable. Vente annulée... ».
3. Vérifier qu'aucun ArticleVendu n'a été créé (rollback atomique).

### Test 5 : jauge pleine
1. Mettre `jauge_max` à un nombre déjà atteint sur l'évènement.
2. La vente en caisse est refusée avec le message de jauge de Lespass.

### Vérifications en base (Lespass)

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import LigneArticle, SaleOrigin
with tenant_context(Client.objects.get(schema_name='<tenant>')):
    for l in LigneArticle.objects.filter(sale_origin=SaleOrigin.LABOUTIK).order_by('-datetime')[:5]:
        print(l.datetime, l.status, l.payment_method, l.amount, l.qty)
"
```

### Tests automatisés

```bash
# Lespass (5 tests, ~7s)
docker exec lespass_django poetry run pytest tests/pytest/test_api_v2_reservation_laboutik.py -v
# Non-régression checkout Stripe
docker exec lespass_django poetry run pytest tests/pytest/test_stripe_reservation.py -v
```

Pas de test automatisé côté LaBoutik pour `methode_BI` (la classe `Commande`
exige un gros contexte de fixtures et la suite existante dépend d'un Fedow
réel). À tester manuellement contre le serveur dev (tests 1-4 ci-dessus).

## Compatibilité

- **Aucune migration** des deux côtés.
- API v2 : `reservationFor` reste accepté et prioritaire ; le mode
  `paymentMethod` est opt-in — les clients API existants ne changent pas.
- Cashless/chèque pour les billets : refusés avec message clair (le cashless
  impliquerait une transaction Fedow, non géré pour l'instant).
- Pas de boucle de synchronisation : la `LigneArticle` créée en `VALID`
  ne re-déclenche pas `send_sale_to_laboutik` (garde `_state.adding`).
- LaBoutik prod tourne en Python 3.8 : le code ajouté est compatible.
