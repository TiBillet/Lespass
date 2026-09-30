# kiosk : plus d'erreur socket.io dans un navigateur, et TPE absent signalé dès l'accueil / kiosk: no more socket.io error in a browser, and missing reader shown on the home screen

**Date :** 2026-09-29
**Migration :** Non / No

## Résumé / Summary

**Quoi / What :**
1. Dans un simple navigateur (`type_app` absent → `unknown`), la borne ne tente plus de joindre
   le serveur NFC local `http://localhost:3000`. socket.io n'est chargé que pour `type_app=pi`
   ou `desktop`. / In a plain browser the kiosk no longer tries to reach `localhost:3000`.
2. Si aucun TPE actif n'est lié à la borne, l'accueil affiche un écran d'erreur au lieu de
   « Posez votre carte ». / Without an active card reader, the home screen shows an error.
3. En DEMO, l'écran d'attente TPE propose « Simuler le paiement » et « Simuler un refus » : ils
   « posent » une carte de test (acceptée 4242… / refusée 4000…0002) sur le TPE Stripe simulé
   (`simulated-wpe`). / In DEMO, two buttons present an accepted or declined test card.

**Pourquoi / Why :**
1. `nfc.js` partait en mode `NFCLO` pour tout `type_app` différent de `cordova`. Chaque page
   affichait « Socket.io - http://localhost:3000 : Error: xhr poll error » + une erreur CORS,
   y compris en prod.
2. L'absence de TPE n'était découverte qu'à l'étape « Payer ».

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `kiosk/static/kiosk/js/nfc.js` | `startLecture` : `cordova` → NFCMC, `pi`/`desktop` → NFCLO, sinon aucun lecteur matériel (le simulateur DEMO reste). |
| `kiosk/templates/kiosk/base.html` | `socket.io.min.js` chargé seulement si `type_app` vaut `pi` ou `desktop`. |
| `kiosk/views.py` | Nouveaux helpers `trouver_la_borne_et_son_tpe` et `terminal_a_un_tpe_actif`. Utilisés par `list` (écran d'accueil) et `refill_with_wisepos` (garde serveur). Repli DEMO inchangé : seulement pour un utilisateur sans borne. |
| `kiosk/templates/kiosk/recharge.html` | Pause → `borne_en_pause`, sinon sans TPE → `borne_sans_tpe`, sinon `etape_poser_carte`. |
| `kiosk/templates/kiosk/partial/borne_sans_tpe.html` | Nouveau : écran d'erreur « la borne ne peut pas encaisser ». |
| `kiosk/views.py` (bis) | Nouvelle action `simuler_paiement` (POST `/kiosk/{pk}/simuler_paiement/`), DEMO uniquement : `stripe.terminal.Reader.TestHelpers.present_payment_method` sur le lecteur du paiement, avec la carte de test choisie par `issue` (`accepte` / `refuse`, sinon 404). 404 hors DEMO, garde d'appartenance comme `cancel`. |
| `kiosk/templates/kiosk/partial/simulation_paiement.html` | Nouveau : boutons « Simuler le paiement » / « Simuler un refus » (DEMO) sur l'écran d'attente TPE, remplacé par un message après le clic. |
| `kiosk/templates/kiosk/waiting_credit_card_terminal.html` | Inclut le bouton de simulation si `demo`. |
| `tests/pytest/test_kiosk_flow.py` | Test socket.io déplacé sur `type_app=pi` ; nouveaux tests : navigateur sans socket.io, accueil sans TPE, accueil avec TPE, simulation de paiement (404 hors DEMO, carte acceptée, carte refusée, issue inconnue, erreur Stripe). |

### Migration
- **Migration nécessaire / Migration required :** Non / No

### Traductions / Translations
Nouvelles chaînes à traduire : « La borne ne peut pas encaisser pour le moment. », « Simuler le paiement », « Simuler un refus » et les messages de simulation (`makemessages` non lancé, à faire par le mainteneur).

### Correctif / Fix — simulation de paiement
`stripe.terminal.Reader.TestHelpers.present_payment_method` était appelé sans `type="card_present"`.
Stripe refusait l'appel (« You have entered a card_present number but no type ») et la borne
affichait « La simulation a échoué ». / The call lacked `type="card_present"`, so Stripe rejected it.

| Fichier / File | Changement / Change |
|---|---|
| `kiosk/views.py` | `simuler_paiement` : ajout de `type="card_present"`. |
| `kiosk/views.py` (bis) | En cas d'échec, le texte brut de l'erreur Stripe est passé au template (`erreur_stripe_brute`). Route DEMO uniquement. |
| `kiosk/templates/kiosk/partial/simulation_paiement.html` | Affiche « Réponse de Stripe : … » sous le message d'erreur. |
| `tests/pytest/test_kiosk_flow.py` | Les assertions du mock vérifient aussi `type="card_present"` ; le test d'erreur vérifie que le texte Stripe est affiché. |

Nouvelle chaîne à traduire / New string : « Réponse de Stripe : ».
