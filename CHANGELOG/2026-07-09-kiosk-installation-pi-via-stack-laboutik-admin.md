# Kiosk : installation Pi via la stack LaBoutik + admin TPE / Kiosk: Pi install via the LaBoutik stack + terminal admin

**Date :** 2026-07-09
**Migration :** Oui / Yes — `kiosk` 0004 (renommage d'affichage uniquement, `AlterModelOptions`)

**Quoi / What :** la borne kiosk sur Raspberry Pi s'installe avec **la stack LaBoutik existante**
(`laboutik_client_pi_desktop_v2/`), sans script ni configuration propres au kiosk. Même matériel, même
lecteur NFC, même client Node. Le seul aiguillage est le **rôle du `PairingDevice`** : un rôle `KI` est
redirigé vers `/kiosk/` par le bridge d'auth, un rôle `LB` vers `/laboutik/caisse/`. §5 du
`kiosk/README.md` réécrite : image Bullseye **arm64**, contournements `sudo env` / `fbturbo` / `env.js`,
service systemd pour `nfcServer.js`, écran en paysage (`setup-laboutik-pi gpio 0`).

**`kiosk/Pi/Makefile`** : `sudo apt install make curl`, `curl -O …/Makefile`, `make conf`, `make install`,
`sudo reboot`. Le Makefile n'installe rien lui-même — il appelle `setup-laboutik-pi` puis applique les
correctifs (fbturbo purgé, cache npm, `env.js`, définition d'écran, service systemd). Il neutralise le
`reboot` en dur du script (faux `reboot` en tête de `PATH`) pour n'avoir qu'un seul redémarrage, à la fin.
`tibillet.conf` (auto-généré, commenté) porte `SERVER`, `SCREEN_WIDTH/HEIGHT`, `ROTATE`, `NFC`, `GIT_BRANCH` —
**pas le code PIN**, qui se saisit sur l'écran tactile.

**Correctif du driver RC522** (`vma405-rfid-rc522.js`) : depuis `b294e695` (6 mai 2026), `nfcServer.js`
attend `{ startListening, stopListening, getStatus }` — le driver Pi n'exposait que `initNfcReader`, donc
`type_app: 'pi'` mourait au démarrage. Le driver expose désormais le contrat, mémorise l'ID du polling
(`stopListening` ne pouvait rien arrêter), renvoie `{ tagId, data }` (le front rejette les lectures dont
`data.uuidConnexion` ne correspond pas) et s'arrête après un tag. **Validé sur matériel** (lecture d'une
carte réelle sur RC522). À relire par `filaos974`.

**Simulateur et lecteur en parallèle** (`kiosk/static/kiosk/js/nfc.js`) : en `DEMO`, `startLecture()`
faisait `simule(); return` et le lecteur physique n'était jamais interrogé. Il affiche désormais le
simulateur **et** démarre le lecteur, comme l'app Android : le premier des deux qui répond gagne, et
`stopLecture()` (appelé par le `willClose` du modal) nettoie les deux.

Côté admin : `Terminal` s'affiche désormais « TPE Bancaire », `StripeLocation` sort de l'admin (créée
automatiquement à l'appairage, comme dans LaBoutik), et le champ « Borne » affiche le nom de la borne au
lieu de son email synthétique, filtré sur le rôle `KI`.

**Pourquoi / Why :** ne pas maintenir deux procédures d'installation pour un matériel identique, et
lever la confusion entre le TPE bancaire Stripe et les terminaux Pi/Sunmi de LaBoutik.

**Non vérifié / Not verified :** lecture NFC réelle sur RC522, appairage complet jusqu'à `/kiosk/`,
paiement TPE. Installation, session X, serveur Node et proxy de claim validés sur Pi 3B+.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `kiosk/README.md` | §5 réécrite : image arm64, contournements, service systemd, statut de validation |
| `laboutik_client_pi_desktop_v2/modules/devices/vma405-rfid-rc522.js` | Aligné sur le contrat de `nfcServer.js` (cf. ci-dessus) |
| `kiosk/models.py` | `Terminal.Meta` : `verbose_name = "TPE Bancaire"` |
| `kiosk/admin.py` | `StripeLocationAdmin` supprimé ; `term_user` filtré sur `KI` et affiché par son nom |
| `discovery/views.py` | `TermUser.first_name = pairing_device.name` à l'appairage |
| `Administration/admin/dashboard.py` | Sidebar : « TPE Bancaires », entrée « Emplacements Stripe » retirée |

---
