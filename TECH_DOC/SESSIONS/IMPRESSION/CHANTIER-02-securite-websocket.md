# CHANTIER 02 — Sécurité du WebSocket d'impression

> **Statut : FAIT (2026-07-14).** 8 tests, 854 tests verts au total. Vérifié en conditions
> réelles : un ticket envoyé via Redis arrive bien sur le canal cloisonné.

Voir [SPEC.md](./SPEC.md) §8.

Fait après le [CHANTIER-01](./CHANTIER-01-terminal-et-routage.md), qui fournit le modèle
`Terminal` sur lequel s'appuie le contrôle d'accès.

## Ce qui a été implémenté

| Fichier | Changement |
|---|---|
| `wsocket/consumers.py` | **Nouvelle** fonction `imprimante_appartient_au_terminal(tenant, user, printer_uuid)` — la règle, écrite en clair et en synchrone. `PrinterConsumer.connect()` ne fait que l'appeler. |
| `laboutik/printing/base.py` | **Nouvelle** fonction `nom_du_groupe_websocket(schema_name, printer_uuid)` — le canal Redis porte le nom du lieu. |
| `laboutik/printing/sunmi_inner.py` | L'émetteur appelle la **même** fonction pour nommer le canal. |
| `tests/pytest/test_impression_securite_websocket.py` | 8 tests. |

**Pourquoi une fonction pure plutôt que la règle dans `connect()`** : elle est lisible et
testable directement. Tester à travers un `WebsocketCommunicator` aurait exigé
`transaction=True`, qui déclenche un `TRUNCATE` — et celui-ci **échoue** sur ce projet, à
cause de la clé étrangère `controlvanne_tireusebec` → `discovery_pairingdevice`.

**Pourquoi une fonction partagée pour le nom du canal** : l'émetteur et le récepteur doivent
le nommer **à l'identique**. S'ils divergeaient, le ticket partirait dans un canal que
personne n'écoute — **sans la moindre erreur**. Un test lit le code source des deux bouts
pour vérifier qu'aucun ne refabrique le nom à la main.

## Le trou

`PrinterConsumer.connect()` (`wsocket/consumers.py:176`) vérifie deux choses :

1. le tenant est résolu ;
2. l'utilisateur est authentifié.

**Et rien d'autre.** Il ne vérifie pas :

- que l'imprimante demandée **existe** ;
- qu'elle appartient au **tenant courant** ;
- que l'utilisateur est un **terminal** (n'importe quel compte humain authentifié passe).

Et le groupe Redis est `printer-{uuid}` (`laboutik/printing/sunmi_inner.py:194`) —
**sans préfixe de tenant**. Redis est partagé par tous les lieux.

Un compte authentifié qui connaît un UUID d'imprimante peut donc rejoindre son groupe et
**lire le contenu des tickets clients**, y compris ceux d'un autre lieu. Les UUID sont en v4,
donc non devinables : ce n'est pas exploitable en aveugle. Mais le contrôle d'accès est vide,
et c'est une donnée client (nom, montants, articles).

## Ce qu'il faut faire

### 1. Contrôler l'accès dans `connect()`

Résoudre le `Printer` **dans le schéma du tenant** — s'il n'existe pas là, fermer. Cela
suffit déjà à bloquer le cross-tenant : une imprimante du lieu B est introuvable dans le
schéma du lieu A.

Puis exiger que l'utilisateur soit **légitime pour cette imprimante** : un `TermUser` dont le
`Terminal` pointe cette imprimante (`terminal.printer`). C'est le cas nominal, et le seul :
la tablette s'abonne à la sienne.

Tout le reste : `close()`.

> **Pas d'exception « admin »** : la fonction « imprimer un ticket de test depuis l'admin »
> **n'existe pas**. `print_test()` est déclaré dans l'interface des backends
> (`laboutik/printing/base.py:57`) mais **n'a aucun appelant** et n'est exposé nulle part.
> Ne pas ouvrir une brèche pour une feature qui n'existe pas. Si elle arrive un jour, elle
> passera par une tâche Celery côté serveur, pas par un abonnement WebSocket admin.

### 2. Cloisonner le groupe Redis par tenant

`printer-{uuid}` → `printer-{schema_name}-{uuid}`, **des deux côtés** :

| Fichier | Rôle |
|---|---|
| `wsocket/consumers.py:209` | Abonnement (`group_add`) |
| `laboutik/printing/sunmi_inner.py:194` | Envoi (`group_send`) |

Défense en profondeur : même si le contrôle d'accès était contourné, un abonné du lieu A ne
serait plus dans le même groupe Redis qu'un émetteur du lieu B.

## Tests (`tests/pytest/test_impression_securite_websocket.py`)

Verrou 1 — seul le propriétaire écoute :
- le terminal propriétaire s'abonne à **son** imprimante ✅
- un terminal ne peut **pas** écouter l'imprimante d'un autre ✅
- un compte **humain** authentifié est refusé (c'était le trou principal) ✅
- un anonyme est refusé ✅
- un terminal **sans imprimante** est refusé ✅
- un identifiant malformé est refusé proprement, sans erreur serveur ✅

Verrou 2 — le canal porte le nom du lieu :
- deux lieux ne partagent jamais un canal, même pour un identifiant d'imprimante identique ✅
- l'émetteur et le récepteur nomment le canal **à l'identique** ✅

**Le cloisonnement entre lieux est obtenu par le verrou 1 lui-même** : le `Terminal` est lu
dans le schéma du lieu courant. Une imprimante du lieu B est introuvable depuis le lieu A —
la table des terminaux n'existe que dans le schéma de son lieu. Le préfixe de tenant sur le
canal Redis est la seconde barrière (défense en profondeur).

## Backlog — le même anti-pattern ailleurs (relecture Fable)

**`LaboutikConsumer`** (`wsocket/consumers.py:54-94`, canal `ws/laboutik/{pv_uuid}/`) porte
exactement le défaut qu'on vient de corriger, en moins grave :

- `connect()` n'a **aucun contrôle d'accès** — ni authentification, ni tenant ;
- le groupe `laboutik-pv-{pv_uuid}` n'a **pas de préfixe de tenant** (celui des jauges,
  `laboutik-jauges-{schema}`, en a un).

**Gravité faible aujourd'hui** : ce canal transporte des jauges, des badges de stock et des
notifications (du HTML pré-rendu), pas le contenu nominatif des tickets. Et `pv_uuid` est un
UUID v4, non devinable. **Mais à traiter le jour où ce canal portera de la donnée sensible.**

**`ChatConsumer`** (`wsocket/consumers.py:571+`) : legacy V1, sans authentification ni tenant.
Vérifier qu'il est mort, et le retirer si c'est le cas.

## Hors périmètre, à noter

**Un PIN d'appairage n'expire jamais.** Le claim ne vérifie que `claimed_at__isnull=True`
(`discovery/serializers.py:36`). Un PIN oublié dans l'admin reste claimable indéfiniment, et
le throttle est **par IP** (contournable en distribué sur un espace de 900 000 valeurs).

Un TTL sur `created_at` (~1 h) serait sain. À traiter dans le
[CHANTIER-03](./CHANTIER-03-unification-appairage.md), qui touche déjà l'appairage.
