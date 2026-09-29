# kiosk : erreur socket.io et TPE absent

## Ce qui a été fait
- `nfc.js` + `base.html` : socket.io (serveur NFC local port 3000) n'est plus utilisé que pour `type_app=pi` ou `desktop`.
- `kiosk/views.py` : `trouver_la_borne_et_son_tpe()` vérifie la borne et son TPE actif. L'accueil (`list`) affiche `partial/borne_sans_tpe.html` si rien n'est lié.

Voir `CHANGELOG/2026-09-29-kiosk-socketio-et-tpe-absent.md`.

## Tests à réaliser

### Test 1 : plus d'erreur socket.io dans un navigateur
1. Ouvrir `/kiosk/` dans Firefox/Chrome (sans `?type_app=`), console ouverte.
2. Attendu : aucune erreur « xhr poll error » ni CORS sur `localhost:3000`. Un `console.warn` « Aucun lecteur NFC materiel » apparaît quand la lecture démarre.
3. En DEMO, le simulateur de cartes fonctionne toujours.

### Test 2 : Pi / desktop inchangés
1. Ouvrir `/kiosk/?type_app=pi` (ou via le bridge du client Pi).
2. Attendu : `socket.io.min.js` chargé, connexion au `nfcServer.js` local comme avant.

### Test 3 : cordova inchangé
1. Borne Sunmi (`?type_app=cordova`) : lecture NFC via le plugin, pas de socket.io chargé.

### Test 4 : borne sans TPE
1. Admin → Terminaux : prendre une borne Kiosque et supprimer/désactiver son TPE (`TPEBancaire.active = False`).
2. Hors DEMO, ouvrir `/kiosk/` avec cette borne.
3. Attendu : écran « La borne ne peut pas encaisser pour le moment. » + « Aucun lecteur de carte bancaire n'est branché sur cette borne. ». Le bouton Admin reste disponible.
4. Rebrancher le TPE → l'accueil revient à « Posez votre carte ».

### Test 5 : bouton « Simuler le paiement » (DEMO)
1. DEMO=1, worker Celery lancé. Sur `/kiosk/`, poser une carte (simulateur), choisir un montant, « Payer ».
2. L'écran d'attente affiche « Simuler le paiement ». Cliquer.
3. Attendu : message « Carte de test présentée… », puis l'écran de succès avec le nouveau solde (WebSocket, ou le sondage de secours sous 10 s).
4. Le crédit de la carte est fait par **Fedow**, sur le webhook Stripe `payment_intent.succeeded`. En local, Stripe ne peut pas joindre Fedow : le solde ne bouge pas tant que le webhook n'est pas relayé vers Fedow (ex. `stripe listen --forward-to <route webhook TPE de Fedow>`, avec le secret affiché renseigné comme `stripe_endpoint_secret` de Fedow).
5. Refus : relancer un paiement, cliquer « Simuler un refus ». Message « Carte refusée présentée… ». Le paiement reste ouvert (comme une vraie carte refusée) : toucher « Annuler » → écran de refus. Sans geste, l'écran de refus arrive à la fin du suivi (120 s).
6. Hors DEMO : les boutons n'apparaissent pas, et `POST /kiosk/{pk}/simuler_paiement/` renvoie 404.

### Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_kiosk_*.py -q
```

## Compatibilité
Repli DEMO inchangé : seul un utilisateur SANS borne (admin dans le navigateur) utilise le TPE de démo. Une borne appairée sans TPE affiche l'erreur, même en DEMO.
