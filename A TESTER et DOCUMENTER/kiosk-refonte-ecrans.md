# Kiosk — nouveaux écrans (maquette TEMP-tibillet-kiosk-main)

## Ce qui a été fait
Voir `CHANGELOG/2026-09-28-kiosk-ecrans-maquette.md`. Le parcours commence par la carte
(solde → montant → récapitulatif → TPE → succès/merci ou refus). Un écran de configuration
s'ouvre avec une carte primaire.

## Préparation
```bash
docker exec lespass_django poetry run python manage.py migrate_schemas
docker exec lespass_django poetry run python manage.py collectstatic --noinput
```
Redémarrer aussi le worker Celery (il ne recharge pas le code tout seul).
Serveur en `DEBUG=1` (donc `DEMO=1`), connecté en admin du tenant `lespass`, ouvrir
`https://lespass.tibillet.localhost/kiosk/`. Le **simulateur de cartes** est replié en bas
de l'écran : cliquer son en-tête pour voir `primary`, `client1`…`client3`, `unknown`.

## Tests à réaliser

### Test 1 : recharge complète
1. Écran « Posez votre carte sur le lecteur. » ; pas de bouton « Recommencer ».
2. Simulateur → `client1` → le solde s'affiche (chez Fedow) avec « carte ·· XXXX ».
3. « Recharger » → cliquer 20 €, puis taper `1`, `2` : le montant passe à « 12 € »
   (la frappe remplace le montant rapide). « Effacer » remet à 0 et désactive Valider.
   Le pavé n'a pas de virgule : euros entiers seulement, 5 chiffres au plus.
   Le serveur refuse aussi les centimes : un POST avec `totalAmount=20.50` affiche
   « Le montant doit être un nombre entier d'euros. »
4. Le bouton affiche « Valider · 12,00 € ». Valider → récapitulatif : « + 12,00 € », nouveau
   solde = solde + 12, bouton « Payer 12,00 € ».
5. « Retour » revient au choix du montant ; Valider à nouveau → écran TPE.
6. Avec le lecteur simulé Stripe (`simulated-wpe`), présenter une carte test → écran succès
   (montant ajouté + nouveau solde), puis « Merci ! » après 6 s, puis retour accueil.

### Test 2 : refus et annulation
1. Aller jusqu'à l'écran TPE : « Recommencer » et « Admin » ont disparu de l'en-tête.
2. Cliquer « Annuler » → « La connexion avec votre banque n'a pas fonctionné. » avec
   « Réessayer » et « Retour à l'accueil ».
3. « Réessayer » relance le paiement du même montant sur la même carte. **Attendre plus de
   30 s sur l'écran TPE** : la page ne doit PAS se recharger toute seule.
4. Sans action sur l'écran de refus, retour automatique à l'accueil après 30 s.

### Test 2 bis : abandon au milieu du parcours
1. Poser `client1`, laisser l'écran du solde (ou le choix du montant, ou le récapitulatif)
   sans y toucher.
2. Après 60 s, la borne revient à « Posez votre carte ». Toucher l'écran relance le délai.

### Test 3 : cartes particulières
1. `unknown` → message « Carte inconnue » sur l'écran 1, le lecteur se relance.
2. Une carte anonyme (non liée à un email) → modale « Votre carte n'est pas enregistrée. »,
   « Continuer » la ferme.

### Test 4 : configuration par carte primaire
1. « Admin » → « Accéder à la configuration » → simulateur `client1` →
   « Ce n'est pas une carte administrateur. » → « Réessayer » → `primary`.
2. Page « Choisissez ce qui tourne ce soir. » : Recharge active, les trois autres « Bientôt ».
3. Couper la recharge → « Aucun service mis en route. », « Démarrer » désactivé.
4. Retaper `/kiosk/` dans l'URL → `/kiosk/` affiche « La borne est en pause. » ; la
   configuration reste ouverte 10 min au plus, puis `/kiosk/configuration/` renvoie à l'accueil.
   Clavier : Tab reste dans la modale admin, Échap la ferme.
5. Retour sur `/kiosk/configuration/`, rallumer, « Démarrer la borne » → `/kiosk/`, et
   `/kiosk/configuration/` renvoie de nouveau à l'accueil.
6. **Note :** un admin sans borne appairée n'a pas de réglages ; la bascule affiche
   « Aucune borne n'est appairée ». Tester l'interrupteur avec une vraie borne KI.

### Test 5 : tailles d'écran
1280×800 (référence) et 1024×600 (Pi 7") : aucun écran du parcours ne défile, et
« Démarrer la borne » est visible sur la configuration. 1920×1080 : échelle agrandie.
375×667 (téléphone) : pas de défilement horizontal.

## Vérifications en base
```bash
docker exec lespass_django poetry run python manage.py tenant_command shell --schema=lespass -c \
  "from kiosk.models import ReglagesBorne, PaymentsIntent; print(list(ReglagesBorne.objects.values())); print(PaymentsIntent.objects.order_by('-datetime').values('amount','solde_avant_centimes','status')[:3])"
```

## Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_kiosk_*.py -v --api-key dummy
```
