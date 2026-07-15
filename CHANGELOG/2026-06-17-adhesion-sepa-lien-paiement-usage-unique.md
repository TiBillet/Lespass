# Adhésion SEPA — lien de paiement à usage unique (anti double prélèvement)

**Date :** 2026-06-17
**Migration :** Oui

## Ce qui a été fait

Une adhésion à validation manuelle envoie un lien de paiement par email. En SEPA,
le débit prend 3 à 14 jours pendant lesquels l'adhésion restait `ADMIN_VALID` et le
lien restait actif → recliquer pouvait recréer un checkout et un 2e prélèvement.

On matérialise désormais l'état « paiement soumis » sur l'adhésion (statut
`PAYMENT_PENDING`). Tant que ce statut est posé, le lien n'ouvre plus de checkout et
affiche une page d'information. Les pages d'erreur JSON 404 sont remplacées par des
pages HTML claires.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | Statut `PAYMENT_PENDING` + bascule dans `update_checkout_status` |
| `BaseBillet/views.py` | `get_checkout_for_membership` : routage par statut + `except` bloquant |
| `ApiBillet/views.py` | `async_payment_failed` : réarmement `PAYMENT_PENDING → ADMIN_VALID` |
| `Administration/admin_tenant.py` | Filtre « Attente de paiement » inclut `PAYMENT_PENDING` |
| `BaseBillet/templates/.../payment_already_pending.html` | Correction block `main` + ordre `extends` |
| `BaseBillet/templates/.../payment_already_done.html` | Nouveau template |
| `BaseBillet/templates/.../payment_link_invalid.html` | Nouveau template |
| `BaseBillet/migrations/0219_alter_membership_status.py` | Nouveau choix de statut |

Migration appliquée en dev (`migrate_schemas`). À appliquer en prod.

## Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_membership_sepa_payment_link.py -v
```
4 tests verts : page « en cours » sans checkout (PP), page « déjà active » (ONCE),
checkout créé (ADMIN_VALID), bascule de statut à la soumission.

Non-régression (22 tests verts) :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stripe_membership_simple.py tests/pytest/test_stripe_membership_complex.py tests/pytest/test_membership_create.py tests/pytest/test_stripe_reservation.py tests/pytest/test_stripe_crowds.py -q
```

E2E (nécessite le serveur via Traefik) :
```bash
docker exec lespass_django poetry run pytest tests/e2e/test_sepa_duplicate_protection.py -v -s
```

## Tests manuels à réaliser

### Test 1 — SEPA : un seul prélèvement possible
1. Produit adhésion à validation manuelle, SEPA activé sur le compte Stripe.
2. Soumettre une demande d'adhésion → admin → « Accepter » → mail de paiement reçu.
3. Cliquer le lien → payer en **SEPA** (mandat) → revenir sur le site.
4. Vérifier en base : `Membership.status == 'PP'` (PAYMENT_PENDING).
5. Recliquer sur le lien du mail → **page « Paiement en cours de traitement »**,
   aucun nouveau checkout Stripe, aucun 2e mandat.

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import Membership
t = Client.objects.get(schema_name='<schema>')
with tenant_context(t):
    m = Membership.objects.filter(user__email='<email>').first()
    print(m.status, [p.get_status_display() for p in m.stripe_paiement.all()])
"
```

### Test 2 — CB : comportement inchangé
1. Même flux, payer en **carte bancaire** → adhésion `ONCE` immédiatement.
2. Recliquer le lien → **page « Votre adhésion est déjà active »** (plus de 404 JSON).

### Test 3 — Échec SEPA : réarmement
1. Simuler un prélèvement SEPA refusé (webhook `async_payment_failed`).
2. Vérifier que l'adhésion repasse `PAYMENT_PENDING → ADMIN_VALID` et que le lien
   permet de relancer un paiement.

### Test 4 — Admin
- Filtre liste adhésions « Attente de paiement » : les adhésions en `PAYMENT_PENDING`
  y apparaissent bien.

## Backfill production (adhésions déjà en cours au déploiement)

Le correctif ne bascule en `PAYMENT_PENDING` que les **nouvelles** soumissions
(via webhook/retour). Les adhésions dont le mandat SEPA était **déjà soumis**
au moment du déploiement restent `ADMIN_VALID` → leur lien pourrait encore
recréer un checkout. Le management command les régularise :

```bash
# 1. Dry-run sur le tenant concerné (n'écrit rien, liste les adhésions) :
docker exec lespass_django poetry run python manage.py backfill_membership_payment_pending --schema <schema>

# 2. Appliquer :
docker exec lespass_django poetry run python manage.py backfill_membership_payment_pending --schema <schema> --apply

# 3. (option) Confirmer en plus via l'API Stripe les cas sans moyen SEPA local :
docker exec lespass_django poetry run python manage.py backfill_membership_payment_pending --schema <schema> --verify-stripe --apply
```

Détection : adhésion `ADMIN_VALID` + paiement `PENDING` dont une ligne est en
`STRIPE_SEPA_NOFED` (preuve que le mandat a été soumis). `--verify-stripe`
ajoute une confirmation via `Session.retrieve` (`status == 'complete'`) pour les
cas où le webhook n'aurait pas posé le moyen de paiement. Sans `--schema`, tous
les tenants (hors ROOT) sont traités. **Dry-run par défaut**, `--apply` requis
pour écrire. Testé en dev (cycle AV → détection → apply → PP).

## i18n
Nouvelles chaînes FR (statut + pages) → `makemessages -l fr/en` puis `compilemessages`
(à faire par le mainteneur).

## Compatibilité
- Le succès final SEPA (`async_payment_succeeded`) passe `PAYMENT_PENDING → ONCE/AUTO`
  via le trigger existant (`triggers.py`, inconditionnel sur le statut de départ).
- Hors périmètre : le cas « deux adhésions distinctes pour la même personne » (relève
  de `max_per_user`).
