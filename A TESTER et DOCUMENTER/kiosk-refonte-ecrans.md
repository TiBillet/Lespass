# Kiosk — nouveaux écrans (maquette TEMP-tibillet-kiosk-main)

## Ce qui a été fait
Voir `CHANGELOG/2026-09-28-kiosk-ecrans-maquette.md`. Le parcours commence par la carte
(solde → montant → récapitulatif → TPE → succès/merci ou refus). Un écran de configuration
s'ouvre avec une carte primaire.

## Préparation
```bash
poetry run python manage.py migrate_schemas
poetry run python manage.py collectstatic --noinput
```
Serveur en `DEBUG=1` (donc `DEMO=1`), connecté en admin du tenant `lespass`, ouvrir
`https://lespass.tibillet.localhost/kiosk/`. Le **simulateur de cartes** est replié en bas
de l'écran : cliquer son en-tête pour voir `primary`, `client1`…`client3`, `unknown`.

## Tests à réaliser

### Test 1 : recharge complète
1. Écran « Posez votre carte sur le lecteur. » ; pas de bouton « Recommencer ».
2. Simulateur → `client1` → le solde s'affiche (chez Fedow) avec « carte ·· XXXX ».
3. « Recharger » → cliquer 20 €, puis taper `5`, `,`, `5` : le montant passe à « 5,5 € »
   (la frappe remplace le montant rapide). « Effacer » remet à 0 et désactive Valider.
4. Valider → récapitulatif : « + 5,50 € » et nouveau solde = solde + 5,50.
5. « Retour » revient au choix du montant ; Valider à nouveau → écran TPE.
6. Avec le lecteur simulé Stripe (`simulated-wpe`), présenter une carte test → écran succès
   (montant ajouté + nouveau solde), puis « Merci ! » après 6 s, puis retour accueil.

### Test 2 : refus et annulation
1. Aller jusqu'à l'écran TPE, cliquer « Annuler » → « La connexion avec votre banque n'a pas
   fonctionné. » avec « Réessayer » et « Retour à l'accueil ».
2. « Réessayer » relance le paiement du même montant sur la même carte.
3. Sans action, retour automatique à l'accueil après 30 s.

### Test 3 : cartes particulières
1. `unknown` → message « Carte inconnue » sur l'écran 1, le lecteur se relance.
2. Une carte anonyme (non liée à un email) → modale « Votre carte n'est pas enregistrée. »,
   « Continuer » la ferme.

### Test 4 : configuration par carte primaire
1. « Admin » → « Accéder à la configuration » → simulateur `client1` →
   « Ce n'est pas une carte administrateur. » → « Réessayer » → `primary`.
2. Page « Choisissez ce qui tourne ce soir. » : Recharge active, les trois autres « Bientôt ».
3. Couper la recharge → « Aucun service mis en route. », « Démarrer » désactivé.
4. Retaper `/kiosk/` dans l'URL → la configuration est toujours ouverte (session) ;
   `/kiosk/` affiche « La borne est en pause. »
5. Retour sur `/kiosk/configuration/`, rallumer, « Démarrer la borne » → `/kiosk/`, et
   `/kiosk/configuration/` renvoie de nouveau à l'accueil.
6. **Note :** un admin sans borne appairée n'a pas de réglages ; la bascule affiche
   « Aucune borne n'est appairée ». Tester l'interrupteur avec une vraie borne KI.

### Test 5 : tailles d'écran
1280×800 (référence, sans scroll), 1920×1080, 1024×600 (Pi 7" : l'écran du montant tient,
la page de configuration défile).

## Vérifications en base
```bash
poetry run python manage.py tenant_command shell --schema=lespass -c \
  "from kiosk.models import ReglagesBorne, PaymentsIntent; print(list(ReglagesBorne.objects.values())); print(PaymentsIntent.objects.order_by('-datetime').values('amount','solde_avant_centimes','status')[:3])"
```

## Tests automatiques
```bash
poetry run pytest tests/pytest/test_kiosk_*.py -v --api-key dummy
```
