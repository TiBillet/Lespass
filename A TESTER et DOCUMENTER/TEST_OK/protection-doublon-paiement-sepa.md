# Protection doublon paiement adhesion (SEPA)

## Ce qui a ete fait

Bug signale en production : des utilisateurs cliquaient plusieurs fois sur le lien
de paiement d'adhesion (recu par email), ce qui creait un nouveau checkout Stripe
a chaque clic. Resultat : doubles prelevements SEPA.

### Modifications

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | `get_checkout_for_membership` : verification d'un paiement Stripe existant avant d'en creer un nouveau. 3 cas geres : session ouverte (reutilise), session complete/SEPA en cours (page info), session expiree (nouveau checkout). |
| `BaseBillet/templates/reunion/views/membership/payment_already_pending.html` | Nouveau template : page d'information affichee quand le prelevement SEPA est deja en cours |
| `CHANGELOG.md` | Entree ajoutee (section 0) |

## Tests a realiser

### Test 1 : Clic unique (comportement normal)

1. Creer une adhesion avec validation manuelle et prix payant
2. Valider l'adhesion depuis l'admin (bouton "Accepter")
3. Ouvrir le lien de paiement recu par email
4. **Verification :** redirige vers le checkout Stripe normalement

### Test 2 : Double clic — session encore ouverte

1. Ouvrir le lien de paiement (redirige vers Stripe)
2. Ne PAS completer le paiement sur Stripe
3. Ouvrir le lien de paiement une deuxieme fois
4. **Verification :** redirige vers la MEME session Stripe (pas de nouveau checkout)

Verification en base :
```bash
docker exec lespass_django poetry run python manage.py shell -c "
from BaseBillet.models import Membership, Paiement_stripe
m = Membership.objects.get(uuid='<UUID>')
print('Nb paiements:', m.stripe_paiement.count())
for p in m.stripe_paiement.all():
    print(f'  {p.uuid} status={p.status} session={p.checkout_session_id_stripe}')
"
```
Doit montrer UN SEUL paiement (pas deux).

### Test 3 : Double clic — apres completion checkout (SEPA en cours)

1. Ouvrir le lien de paiement et completer le checkout Stripe (choisir SEPA)
2. Ouvrir le lien de paiement une deuxieme fois
3. **Verification :** affiche la page "Paiement en cours de traitement" avec :
   - Message expliquant que le SEPA peut prendre 14 jours
   - Recapitulatif de l'adhesion (produit, montant)
   - Liens "Voir les adhesions" et "Retour a l'accueil"
4. **Verification :** PAS de nouveau paiement cree en base

### Test 4 : Session expiree (24h+ apres)

1. Creer un paiement via le lien (redirige vers Stripe)
2. Attendre que la session Stripe expire (24h) OU expirer manuellement via Stripe Dashboard
3. Ouvrir le lien de paiement
4. **Verification :** un NOUVEAU checkout est cree (l'ancien est marque EXPIRE en base)

### Test 5 : Paiement deja encaisse

1. Completer un paiement d'adhesion jusqu'au bout (webhook recu, membership en status ONCE)
2. Ouvrir le lien de paiement
3. **Verification :** page 404 (le membership n'est plus en status ADMIN_VALID)

## Compatibilite

- Pas de migration necessaire
- Compatible avec les paiements par carte ET par SEPA
- Les paiements deja en cours ne sont pas impactes
- Le template utilise `base_template` (fonctionne en HTMX et en pleine page)
