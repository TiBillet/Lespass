# Tireuse : badge reconnu plus vite, nouvel essai après une erreur réseau / Tap: faster badge, retry after a network error

**Date :** 2026-11-19
**Migration :** Non

## Resume / Summary
**Quoi / What :** le Pi de la tireuse garde sa connexion au serveur ouverte d'un appel à l'autre. Une carte posée est autorisée en 0,4 à 0,6 s au lieu de 1,6 à 2,0 s (mesuré sur une tireuse réelle). Si `authorize` échoue sur une erreur réseau, le Pi réessaie toutes les 2,5 s tant que la carte reste posée : il n'est plus nécessaire de la retirer puis de la reposer. Si la carte est retirée pendant l'échec, `card_removed` part et l'écran revient à « En attente ». Une réponse du serveur, même en erreur (page HTML 500), n'est jamais réessayée : elle compte comme un refus. Les cookies ne sont plus gardés. Après 60 s sans appel, `authorize` repart d'une connexion neuve.
/ The tap Pi keeps its server connection open between calls: a badge is authorized in 0.4-0.6 s instead of 1.6-2.0 s. A network error on `authorize` is retried every 2.5 s while the card stays; removing the card sends `card_removed`. A server answer, even an HTML 500, is never retried. No cookies are kept. After 60 s idle, `authorize` opens a fresh connection.

**Pourquoi / Why :** chaque appel ouvrait une nouvelle connexion chiffrée (environ 1,1 s depuis un Pi en 4G). Le délai de 2 s de `authorize` était presque atteint. S'il était dépassé, l'écran pouvait afficher « autorisé » avec la vanne fermée, et la carte restait ignorée jusqu'à son retrait. Le nouvel essai se limite aux erreurs réseau : réessayer une réponse 500 relancerait à chaque fois la clôture d'une session orpheline côté serveur, donc sa facturation.
/ Each call opened a new encrypted connection (about 1.1 s on 4G); the 2 s `authorize` timeout was nearly reached, leaving a "dead" card and a lying screen. Retries are limited to network errors: retrying a 500 would re-run the orphan session closing, hence its billing.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/Pi/network/backend_client.py` | `requests.Session()` partagée par les 4 appels, via `_post()`. Cookies bloqués (`DefaultCookiePolicy(allowed_domains=[])`). `authorize` : délais `(3.0, 4.0)`, connexion neuve après `IDLE_RECONNECT_S` (60 s) sans appel, `BackendError` seulement sur une erreur réseau (`requests.exceptions.RequestException`), réponse non JSON traitée comme un refus. |
| `controlvanne/Pi/controllers/tibeer_controller.py` | Après une `BackendError` d'`authorize` : la carte reste la carte courante, l'indicateur `authorize_a_refaire` relance `authorize` à la lecture suivante, après une pause de `AUTHORIZE_RETRY_DELAY_S` (2,5 s, sous la limite serveur de 30 `authorize` par minute). Le retrait de la carte envoie `card_removed` et remet l'indicateur à zéro. |

---

## Comment tester (a la main) / Manual test

Sur le Pi : arrêter le service (`sudo systemctl stop tibeer`), puis lancer `main.py` à la main pour voir le journal en direct :
`cd ~/tibeer/controlvanne/Pi && .venv/bin/python main.py`

### Test 1 — scenario nominal : badge rapide
1. Poser une carte connue, la retirer. Recommencer 3 fois.
2. Dans le journal, comparer l'heure de « Nouveau badge detecte » et celle de « Autorise ».
3. Attendu : environ 0,4 à 0,7 s par badge (au lieu de 1,6 à 2,0 s avant). Le premier badge est aussi rapide : la connexion a été ouverte au démarrage par `ping`.

### Test 2 — coupure réseau, carte laissée posée
1. Dans un second terminal, couper l'accès au serveur sans couper la session SSH :
   `IP=$(getent hosts <domaine-du-serveur> | cut -d' ' -f1); sudo ip route add blackhole $IP`
2. Poser la carte et **ne plus la toucher**.
3. Attendu : « Erreur backend authorize … nouvel essai a la prochaine lecture », environ toutes les 3 s. La vanne reste fermée.
4. Rétablir l'accès, carte toujours posée : `sudo ip route del blackhole $IP`
5. Attendu : « Autorise … Vanne ouverte » arrive seul, sans retirer la carte (environ 2 s : la connexion est rouverte).

### Test 3 — coupure réseau, carte retirée
1. Couper l'accès comme au test 2. Poser la carte, attendre une ligne « Erreur backend authorize ».
2. Rétablir l'accès, puis retirer la carte.
3. Attendu : « Badge … retire. » dans le journal, et l'écran de la tireuse revient à « En attente » (il ne reste pas figé sur « autorisé »).

### Test 4 — cas limites
- Réponse illisible du serveur (page d'erreur HTML, HTTP 500) : le journal affiche « Authorize : reponse illisible du serveur (HTTP 500) » et la carte est traitée comme refusée, **sans nouvel essai**. Difficile à provoquer à la main ; vérifié avec un serveur HTTP de test local.
- Après plus de 60 s sans badge, le badge suivant reprend environ 1 à 2 s (connexion neuve), puis les suivants redeviennent rapides.
- Fin des tests : vérifier qu'aucune route trou noir ne reste (`ip route | grep blackhole` ne doit rien renvoyer), puis `sudo systemctl start tibeer`.

### Verifs DB / Playwright
- Côté serveur, une session créée par un `authorize` dont la réponse s'est perdue est close à 0 ml au `authorize` suivant (`_cloturer_sessions_orphelines`) : vérifiable dans l'admin des sessions de la tireuse.
- Pas de test automatique dans cette PR : le contrôleur ne s'importe pas encore sans le matériel du Pi. Les tests arriveront avec le harnais de tests du client Pi (faux lecteur, fausse vanne, faux débitmètre, faux client).
