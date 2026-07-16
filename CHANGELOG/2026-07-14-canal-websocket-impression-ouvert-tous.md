# Le canal WebSocket d'impression n'est plus ouvert à tous / The print WebSocket channel is no longer open to everyone

**Date :** 2026-07-14
**Migration :** **Non**
**Spec :** [`TECH_DOC/SESSIONS/IMPRESSION/CHANTIER-02`](TECH_DOC/SESSIONS/IMPRESSION/CHANTIER-02-securite-websocket.md)

**Quoi / What :** `PrinterConsumer.connect()` (`ws/printer/<uuid>/`) ne vérifiait que deux
choses : le lieu est résolu, et l'utilisateur est authentifié. **Rien d'autre.** Il ne
vérifiait ni que l'imprimante existait, ni qu'elle appartenait au lieu, ni que l'utilisateur
était un terminal.

**Pourquoi / Why :** ce canal transporte le **contenu des tickets clients** — noms, montants,
articles. Tout compte authentifié qui connaissait un identifiant d'imprimante pouvait
rejoindre son canal et **les lire en clair**. Y compris ceux d'un **autre lieu** : le canal
Redis s'appelait `printer-<uuid>`, sans le nom du lieu, et Redis est partagé par tous. Les
identifiants sont des UUID v4, donc non devinables — ce n'était pas exploitable en aveugle,
mais le contrôle d'accès était vide.

Deux verrous désormais :

1. **Seul le terminal propriétaire de l'imprimante peut s'abonner.** La règle est écrite en
   clair dans `imprimante_appartient_au_terminal()`. Elle lit le `Terminal` **dans le schéma
   du lieu courant** — ce qui rend, à elle seule, une imprimante d'un autre lieu introuvable.
2. **Le canal Redis porte le nom du lieu** (`printer-<lieu>-<uuid>`). Défense en profondeur.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `wsocket/consumers.py` | **Nouvelle** fonction `imprimante_appartient_au_terminal()`. `PrinterConsumer.connect()` l'appelle et ferme la connexion si elle répond non |
| `laboutik/printing/base.py` | **Nouvelle** fonction `nom_du_groupe_websocket()` — le canal porte le nom du lieu |
| `laboutik/printing/sunmi_inner.py` | L'émetteur appelle la **même** fonction pour nommer le canal |
| `tests/pytest/test_impression_securite_websocket.py` | **Nouveau** — 8 tests |

### Attention / Heads-up

**Un gestionnaire connecté dans un navigateur ne peut plus s'abonner à un canal d'impression.**
C'est le trou que ce chantier ferme, mais si un outil de debug s'appuyait dessus, il cessera
de fonctionner.
