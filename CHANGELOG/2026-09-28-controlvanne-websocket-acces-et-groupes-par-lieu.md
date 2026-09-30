# controlvanne : WebSocket des kiosks — contrôle d'accès, groupes par lieu, suppression de KioskTokenView

**Date :** 2026-09-28
**Migration :** Non / No (`makemigrations --check` : « No changes detected »)

## Résumé / Summary

**Quoi / What :** points 1.1 et 1.2 de l'audit du 2026-09-26
(`CHANGELOG/a traiter/controlvanne-audit-securite-facturation.md`), corrigés
ensemble car ils touchent les mêmes fonctions.

- **1.1 — Contrôle d'accès du WebSocket.** `PanelConsumer.connect()` acceptait
  tout le monde. Désormais, la connexion est refusée **avant** d'être
  acceptée (handshake 403) dans ces cas :
  - le lieu est inconnu (`scope["tenant"]` vaut `None`) ;
  - le visiteur n'est ni un kiosk (session `controlvanne_authenticated`), ni
    un admin du lieu ;
  - le slug n'est ni `all`, ni l'UUID d'une tireuse **de ce lieu**.
  La règle d'accès est commune avec la page du kiosk : `peut_voir_les_kiosks`,
  dans le nouveau `controlvanne/acces.py`. `_verifier_authentification_kiosk`
  l'utilise aussi.
- **1.2 — Groupes Channels par lieu.** Redis est partagé par tous les lieux,
  et l'ancien groupe `rfid_state.all` était **commun à tous** : une liste de
  tireuses d'un lieu recevait les badges des autres lieux (prénom, UID, solde).
  Les groupes sont maintenant `rfid_state.<uuid lieu>.all` et
  `rfid_state.<uuid lieu>.<uuid tireuse>` (nouveau `controlvanne/groupes_ws.py`).
  Les trois envois passent tous par une seule fonction, `pousser_aux_kiosks` :
  - `viewsets._push_ws_kiosk` ;
  - `signals.demander_rechargement_des_kiosks` ;
  - `signals.pousser_snapshot_apres_commit`.
  Le lieu est fixé au moment de l'événement, avant le `on_commit`.
- **Session du kiosk prolongée** : quand une session kiosk est acceptée, le
  consumer l'enregistre. Un kiosk reste des semaines sur la même page sans
  requête HTTP, alors que seul le HTTP prolongeait la session.
- **Robustesse** : `disconnect()` ne plante plus quand la connexion a été
  refusée (pas de groupe). `uuid_du_lieu_courant()` fonctionne aussi sous
  `schema_context` (un `FakeTenant` sans uuid).

/ 1.1 WebSocket refused before accept unless kiosk session or venue admin, with
a valid slug (shared rule with the page, `acces.py`). 1.2 Channels groups named
per venue (`groupes_ws.py`), all senders through `pousser_aux_kiosks`.

**Pourquoi / Why :** n'importe quel navigateur, même non connecté, pouvait
ouvrir `wss://<lieu>/ws/rfid/all/` et recevoir les passages de carte de **tous**
les lieux.

**Vérifié sur le serveur de dev** (handshake brut en HTTP/1.1) :
`/ws/rfid/all/` anonyme → `403 Forbidden` ; avec une session kiosk →
`101 Switching Protocols`.

## Point 1.3 — Suppression de `KioskTokenView`

- **Quoi :** la vue `KioskTokenView` et sa route
  `/controlvanne/kiosk-token/<token>/` sont supprimées. Elles n'étaient
  utilisées nulle part : le Pi ouvre `kiosk/<uuid>/?kiosk_token=<jeton>`
  (`Pi/main.py`, `Pi/config/xinitrc.bash`), et c'est la page du kiosk qui
  consomme le jeton. Aucune version du Pi présente dans le dépôt, depuis le
  commit d'import `f1308e8d6`, n'a appelé cette route. Les Pi se mettent à jour
  à chaque démarrage (`git-update.sh`).
- **Pourquoi :** son paramètre `next` n'était pas validé (redirection ouverte,
  et `javascript:` exécuté via `window.location.replace`). Une route inutilisée
  est une surface d'attaque en trop.
- **Commentaires corrigés** : ils prétendaient que le Pi ouvrait
  `/controlvanne/kiosk-token/<token>/` :
  - docstring et commentaires de `AuthKioskView` (`viewsets.py`), qui décrivent
    maintenant le vrai parcours et le fait que le jeton passe en query string
    (usage unique, 5 minutes) ;
  - docstring de `auth_kiosk` (`Pi/network/backend_client.py`) ;
  - arborescence de `controlvanne/README.md`.
  `Synthese_merge_vs_chantiers.md` n'est pas modifié : c'est un historique.
- **Vérifié sur le serveur de dev :** l'ancienne route renvoie 404. Le vrai
  parcours marche : jeton obtenu par `auth-kiosk`, puis page du kiosk à 200
  avec `?kiosk_token=`, rechargement par cookie à 200. Un jeton réutilisé
  renvoie 403 (usage unique).
- Test : `test_12b_route_kiosk_token_supprimee` (`test_controlvanne_api.py`).
- Bonus : l'import inutilisé `HttpResponseRedirect` signalé par ruff disparaît
  avec la vue.

## Déploiement / Deployment

Les kiosks déjà ouverts sont abonnés aux anciens noms de groupes. Le
redémarrage de daphne ferme leur WebSocket, et `ecran_tireuse.js` se
reconnecte tout seul (1 s → 30 s) sur les nouveaux noms. Un kiosk légitime a
une session kiosk (ou un admin connecté) : il est accepté. Rien à faire à la
main.

## Fichiers / Files

| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/acces.py` | Nouveau : `peut_voir_les_kiosks` (règle commune page + WebSocket) |
| `controlvanne/groupes_ws.py` | Nouveau : noms des groupes par lieu, `uuid_du_lieu_courant`, `pousser_aux_kiosks` |
| `controlvanne/consumers.py` | `connect()` : lieu, accès, slug (UUID d'une tireuse du lieu), groupe par lieu, session prolongée ; `disconnect()` gardé |
| `controlvanne/viewsets.py` | `_push_ws_kiosk` → `pousser_aux_kiosks` ; `_verifier_authentification_kiosk` utilise la règle commune |
| `controlvanne/signals.py` | Les deux envois → `pousser_aux_kiosks`, lieu fixé avant `on_commit` |
| `controlvanne/routing.py`, `controlvanne/README.md` | Documentation des groupes et de l'accès |
| `tests/pytest/test_controlvanne_ws.py` | Nouveau : 8 tests du consumer (anonyme, lieu inconnu, kiosk, admin, admin d'un autre lieu, slug invalide, isolation entre lieux, écran d'une tireuse) |
| `tests/pytest/test_controlvanne_ecran_calibration.py` | Tests de rechargement adaptés aux groupes par lieu |
| `controlvanne/viewsets.py`, `controlvanne/urls.py` | Suppression de `KioskTokenView` et de sa route ; commentaires de `AuthKioskView` corrigés |
| `controlvanne/Pi/network/backend_client.py` | Docstring de `auth_kiosk` corrigée (vrai parcours `?kiosk_token=`) |
| `tests/pytest/test_controlvanne_api.py` | `test_12b` : l'ancienne route renvoie 404 |

## À tester / To test

1. Ouvrir la liste des tireuses de deux lieux dans deux onglets
   (`/controlvanne/kiosk/`). Badger dans le lieu A : rien n'apparaît dans le
   lieu B.
2. Dans la console d'un navigateur **non connecté** :
   `new WebSocket("wss://<lieu>/ws/rfid/all/")` → fermé tout de suite.
3. Sur un vrai Pi : après un redémarrage de daphne, le kiosk se reconnecte et
   reçoit toujours ses messages.

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_ws.py tests/pytest/test_controlvanne_*.py -q
```
