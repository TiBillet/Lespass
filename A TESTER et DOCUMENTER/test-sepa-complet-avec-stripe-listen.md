# Test SEPA complet avec `stripe listen`

## Contexte

Le test `36-sepa-duplicate-protection.spec.ts` couvre la **protection contre les doublons de paiement SEPA** pour les adhesions. Cependant, il ne peut pas tester le flow complet Stripe car :

1. Les sessions Stripe de test (`cs_test_fake_*`) ne sont pas recuperables via `stripe.checkout.Session.retrieve()`
2. Le flow SEPA necessite une redirection vers Stripe Checkout, un paiement reel (ou simule), puis un webhook de retour
3. Sans `stripe listen` actif, les webhooks Stripe ne sont jamais recus par l'application

## Ce qui est teste actuellement (sans Stripe)

- Existence du template `payment_already_pending.html`
- Presence des attributs `data-testid` dans le template
- Une adhesion deja payee retourne 404 sur le lien de paiement

## Ce qu'il faudrait tester avec `stripe listen`

### Scenario 1 : Flow normal SEPA
1. Creer une adhesion en status `ADMIN_VALID` (prete pour paiement)
2. Appeler `GET /memberships/<uuid>/get_checkout_for_membership/`
3. Suivre la redirection vers Stripe Checkout
4. Completer le paiement avec la methode SEPA test (`AT611904300234573201`)
5. Verifier que le webhook `checkout.session.completed` est recu
6. Verifier que l'adhesion passe en status `ONCE` (paye)

### Scenario 2 : Double paiement SEPA
1. Creer une adhesion et lancer un premier checkout
2. Le paiement SEPA reste en `processing` (status Stripe = `complete` mais pas `paid`)
3. Tenter un 2e appel a `get_checkout_for_membership`
4. Verifier que la page `payment_already_pending` est affichee (pas de 2e session Stripe)

### Scenario 3 : Session expiree
1. Creer une adhesion avec une session Stripe expiree
2. Appeler `get_checkout_for_membership`
3. Verifier qu'une nouvelle session est creee (pas blocage sur l'ancienne)

## Comment lancer `stripe listen`

### Pre-requis
```bash
# Installer le CLI Stripe
# https://stripe.com/docs/stripe-cli
brew install stripe/stripe-cli/stripe  # macOS
# ou
sudo apt install stripe  # Debian/Ubuntu
```

### Lancer le forward des webhooks
```bash
# Dans un terminal separe, lancer :
stripe listen --forward-to https://tibillet.localhost/api/webhook_stripe/ --skip-verify

# Le CLI affiche une cle webhook signing secret (whsec_...)
# Cette cle doit correspondre a STRIPE_ENDPOINT_SECRET dans .env
```

### Cartes et methodes de test SEPA
- IBAN test (succes) : `AT611904300234573201`
- IBAN test (echec) : `AT861904300235473202`
- Carte classique : `4242 4242 4242 4242`, exp `12/42`, CVC `424`

### Lancer le test E2E complet
```bash
# Terminal 1 : stripe listen
stripe listen --forward-to https://tibillet.localhost/api/webhook_stripe/ --skip-verify

# Terminal 2 : test Playwright
cd tests/playwright
yarn playwright test --project=chromium tests/36-sepa-duplicate-protection.spec.ts
```

## Architecture du code concerne

- **Vue** : `BaseBillet/views.py` → `get_checkout_for_membership()`
  - Verifie s'il existe deja une session Stripe `PENDING` ou `complete`
  - Si oui et session toujours valide → affiche `payment_already_pending.html`
  - Si session expiree → en cree une nouvelle
  - Si pas de session → cree la premiere session Stripe
- **Template** : `BaseBillet/templates/reunion/views/membership/payment_already_pending.html`
- **Webhook** : `PaiementStripe/views.py` → traitement du `checkout.session.completed`

## Note sur le template

Le template `payment_already_pending.html` a actuellement un bug de syntaxe Django (`{% extends %}` n'est pas le premier tag). Il faudra le corriger avant de pouvoir le tester via `get_template()` dans Django shell.
