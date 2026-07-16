# Stripe Checkout — gestion de l'erreur "account or business name"

**Date :** 2026-05-13
**Migration :** Non

## Contexte

Quand un tenant essaie de souscrire une adhesion (ou de reserver un evenement payant) sur
un compte Stripe Connect dont le `business_profile.name` n'est pas renseigne, Stripe leve
`InvalidRequestError: In order to use Checkout, you must set an account or business name`.

Avant ce fix : 500 cote utilisateur.
Apres ce fix : message clair + redirect vers la page precedente.

## Ce qui a ete fait

### 1) Catch explicite dans `CreationPaiementStripe._checkout_session()`

Avant, l'exception tombait dans le fallback `else` qui retentait avec `force=True` sur les
line_items (corrige rien, c'est un probleme de compte). Maintenant, le cas est detecte
explicitement et leve une `serializers.ValidationError` avec un message generique.

Le `logger.error(...)` inclut le `schema_name` du tenant pour que Sentry remonte
l'incident et que l'admin sache ou intervenir.

### 2) Decision : pas de patch preventif cote Lespass

On a envisage de pre-remplir `business_profile.name` dans
`Configuration.get_stripe_connect_account()`. **Decision finale : non.** Le bug racine est
gere cote Stripe (le gerant doit completer son `business_profile.name` lors du onboarding,
le dashboard Stripe le demande explicitement). Cote Lespass, on se contente de remonter
l'erreur a l'utilisateur et de logger pour Sentry.

`Configuration.get_stripe_connect_account()` reste donc inchange.

### Modifications

| Fichier | Changement |
|---|---|
| `PaiementStripe/views.py` | Nouveau `elif 'account or business name' in str(e).lower()` dans `_checkout_session()`. Loggue le `schema_name` du tenant (Sentry). |
| `CHANGELOG.md` | Entree v1.7.18 |

## Tests a realiser

### Test 1 : Ancien tenant cassé — message UX au lieu du 500

Prerequis : un tenant existant avec un `stripe_connect_account` (ex: `acct_XXX`) dont le
`business_profile.name` est vide.

1. Se connecter en tant qu'utilisateur final (admin@admin.com).
2. Aller sur `https://<tenant>/memberships/`.
3. Cliquer sur une adhesion payante, remplir le formulaire, soumettre.
4. **Attendu** : la page se recharge avec un toast/message d'erreur
   « Online payment is temporarily unavailable. Please contact the site administrator. »
   et NON un 500.
5. Verifier les logs serveur : ligne
   `ERROR Stripe account misconfigured for tenant <schema_name>: ...`

### Test 2 : Fix de production via stripe-cli

Pour fixer un tenant deja casse sans toucher au code :

```bash
# 1. Retrouver l'acct_id du tenant
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import Configuration
t = Client.objects.get(schema_name='<schema>')
with tenant_context(t):
    cfg = Configuration.get_solo()
    print(cfg.stripe_connect_account, '/', cfg.stripe_connect_account_test)
"

# 2. Patcher via stripe-cli (apres `stripe login`)
stripe accounts update acct_XXX \
  -d "business_profile[name]=Nom Commercial"

# 3. Verifier
stripe accounts retrieve acct_XXX | grep -A2 business_profile
```

### Test 3 : Verification que le retry SEPA fonctionne toujours

Le nouveau `elif` est intercale entre `sepa_debit` et `total amount due` — l'ordre des
branches est important. Faire un paiement classique pour confirmer que le flow nominal
n'est pas casse.

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stripe_membership_*.py -v
```

## Compatibilite

- **Backwards compatible** : aucune modification des comptes Connect existants. On ne
  fait que rattraper l'erreur cote utilisateur.
- **Pas de migration DB** : le changement est purement applicatif.
- **Erreur affichee** : message en anglais (passe par `_()`) — sera traduit en francais
  apres `makemessages` + `compilemessages`.
