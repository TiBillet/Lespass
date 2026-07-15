# Le terminal existe avant l'appareil : un seul écran pour tout le matériel / The terminal exists before the device

**Date :** 2026-07-14
**Migration :** **Oui** — `laboutik/0003` (rôle du terminal) et `laboutik/0004` (unicité du TPE).
`migrate_schemas --executor=multiprocessing`
**Spec :** [`TECH_DOC/SESSIONS/IMPRESSION/CHANTIER-05`](TECH_DOC/SESSIONS/IMPRESSION/CHANTIER-05-le-terminal-preexiste.md)

### 1. L'admin mentait

**Quoi / What :** cliquer sur « Terminaux matériels → Terminaux » affichait des **codes PIN**,
pas du matériel. Le vrai écran des terminaux était enterré sous « Kiosque → TPE Bancaires » —
et invisible pour un lieu sans module kiosque.

**Pourquoi / Why :** quand `kiosk.Terminal` est devenu `laboutik.Terminal`, le lien de la
sidebar a été repointé pour ne pas casser, **mais l'entrée n'a été ni renommée ni déplacée**.

Pire : le code PIN d'une tireuse s'affichait **à deux endroits**. La liste « Appairage » n'avait
aucun filtre — le gestionnaire y voyait apparaître des lignes qu'il n'avait jamais créées.

### 2. Le renversement : le claim ne crée plus le terminal, il le remplit

**Quoi / What :** un `Terminal` se **crée dans l'admin** (nom + type d'appareil). Cette création
fabrique un **code PIN**, qui s'affiche dans la colonne « État ». On tape ce code sur l'appareil,
et le claim **remplit** le terminal — il lui pose son compte et sa clé.

**Pourquoi / Why :** tant que le terminal naissait du claim, il n'existait **rien**, avant
l'appairage, sur quoi afficher le code. C'est pour ça que `PairingDevice` devait être visible.

`term_user` vide = **en attente d'appairage**. `term_user` posé = **appairé**.

**`PairingDevice` sort de l'admin.** Il reste en base — il *doit* vivre dans le schéma public,
le claim arrivant sur une route publique où l'appareil ne connaît pas encore son lieu — mais ce
n'est plus qu'une plomberie. `discovery/admin.py` est volontairement **vide**, et le dit.

### 3. Le Raspberry Pi crame : le terminal survit

**Quoi / What :** action « **Générer un nouveau code PIN** » sur un terminal.

**Pourquoi / Why :** elle révoque l'appareil actuel — son compte **et** sa clé, car la clé est
stockée dessus —, détache le compte, et refabrique un code. **Le terminal survit** : il garde
son imprimante, et la tireuse qui le désigne garde toute sa configuration et son historique.

**Le matériel est jetable, le métier persiste.**

### 4. Un lecteur de carte n'appartient qu'à un seul terminal

**Quoi / What :** `Terminal.stripe_id` devient **unique**, et le formulaire refuse un code
d'enregistrement déjà utilisé.

**Pourquoi / Why :** sans ça, deux caisses pourraient croire piloter le même TPE. Un client
verrait s'afficher, sur le lecteur qu'il a devant lui, **le montant de la vente d'à côté** — et
pourrait la payer.

Il n'y a **pas** de page « TPE bancaires » : un TPE n'est pas un objet, c'est une **capacité**
du terminal. On l'active en éditant le terminal. La sidebar tient en deux entrées :
**Terminaux + Imprimantes**.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/models.py` | `Terminal.terminal_role`, `est_appaire()`, `code_pin_en_attente()`, `stripe_id` **unique** |
| `discovery/services.py` | **Nouveau** — `fabriquer_le_code_pin_d_appairage()` |
| `discovery/views.py` | Le claim **remplit** au lieu de créer. Transaction atomique |
| `discovery/admin.py` | **Vidé** — `PairingDevice` sort de l'admin |
| `controlvanne/signals.py` | La tireuse fabrique son `Terminal` et son code PIN |
| `controlvanne/models.py` | `TireuseBec.terminal` posé **à la création**, plus au claim |
| `controlvanne/admin.py` | Le code PIN passe en **change view** |
| `Administration/admin/laboutik.py` | Création autorisée, colonne « État » avec le PIN, action « Générer un nouveau code PIN », unicité du lecteur |
| `Administration/admin/dashboard.py` | Sidebar : **Terminaux + Imprimantes** |

### Deux pièges, pour mémoire / Two traps, for the record

**Une fonction, pas un signal.** Un `post_save` sur `Terminal` aurait fabriqué un code PIN à
chaque création — y compris dans les tests, qui créent des terminaux directement, sous un
`FakeTenant` où la clé étrangère `tenant` ne peut pas être posée. Il aurait fallu trois gardes
empilés. La fabrication du code est donc un **appel explicite**, depuis trois endroits nommés.

**`self.instance.pk` ne dit PAS si l'objet est neuf.** `Terminal.id` est un
`UUIDField(default=uuid4)` : le PK est **déjà rempli** sur une instance neuve. Tester `pk` faisait
croire au formulaire de création qu'il était en édition. **Le bon test est `_state.adding`** —
même piège que `TermUser.save()`.
