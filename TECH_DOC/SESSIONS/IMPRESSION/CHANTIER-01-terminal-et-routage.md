# CHANTIER 01 — `Terminal` et routage de l'impression

> ⚠️ **RÉVISÉ par les chantiers [05](./CHANTIER-05-le-terminal-preexiste.md) et
> [06](./CHANTIER-06-extraction-tpe.md).**
>
> Deux choses que ce document décrit ont changé :
> - **Le claim ne crée plus le `Terminal`** ; il est créé dans l'admin (ce qui fabrique son
>   code PIN) et le claim le **remplit**. `has_add_permission` n'est plus `False` (05).
> - **Le TPE bancaire n'est plus des champs sur `Terminal`** (`registration_code`,
>   `stripe_id`, `type`) : c'est un modèle à part, `TPEBancaire` (06).
>
> Ce qui tient : le routage de l'impression par terminal, la suppression de
> `PointDeVente.printer`, l'abonnement WebSocket, la fonction `imprimante_du_terminal()`.

Voir [SPEC.md](./SPEC.md) pour le contexte et les décisions.

**Objectif** : l'imprimante du ticket client passe du point de vente au terminal. Le
symptôme visé est la **multiplication des tickets** (20 tablettes sur un PV = 20 copies).

> **Prérequis à confirmer** : `kiosk` est-il en production ? Voir [SPEC §10](./SPEC.md#10-hypothèse-à-confirmer-avant-le-chantier-01).
> La réponse conditionne la stratégie de migration (déplacement simple vs `SeparateDatabaseAndState`).

## 1. Modèle — promouvoir `kiosk.Terminal`, ne pas en créer un second

**Ne pas créer un nouveau modèle `Terminal`.** `kiosk.Terminal` (`kiosk/models.py:57`) existe,
porte déjà `name`, `id` (UUID) et `term_user` (OneToOne vers `TibilletUser`,
`related_name="terminal"`, l.74), et vit dans le schéma tenant.

Un second modèle avec le même `related_name` provoquerait un **`fields.E304`** — Django
refuserait de démarrer.

### Le déplacement

`kiosk.Terminal` → `laboutik.Terminal`, avec un champ en plus :

```python
# laboutik/models.py — à placer APRES la classe Printer (qui finit l.346)
class Terminal(models.Model):
    """
    Un appareil appaire : tablette Sunmi, Raspberry Pi, borne libre-service.
    / A paired device: Sunmi tablet, Raspberry Pi, self-service kiosk.

    LOCALISATION : laboutik/models.py

    Cree au moment du claim (discovery/views.py:_create_laboutik_terminal), qui tourne
    deja dans un tenant_context. Porte les CAPACITES MATERIELLES de l'appareil :
    une imprimante, et/ou un TPE Stripe. Les deux sont optionnelles.

    Le compte d'authentification (TermUser) et le PIN d'appairage (PairingDevice) vivent
    dans le schema public : ils ne peuvent pas porter de FK vers Printer, qui est une
    table tenant. C'est la raison d'etre de ce modele. Voir SPEC.md section 3.
    """
    id = models.UUIDField(primary_key=True, default=uuid_module.uuid4, editable=False)

    # Nom lisible, recopie depuis PairingDevice.name au moment du claim.
    # On ne garde PAS de FK vers PairingDevice : elle n'a aucun usage a l'execution,
    # et un menage des PIN consommes dans l'admin detruirait la config de ce terminal.
    # / Human-readable name, copied from PairingDevice.name at claim time.
    name = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("Nom"))

    # FK vers TibilletUser CONCRET, pas le proxy TermUser : le manager de TermUser filtre
    # par tenant et casserait l'acces hors contexte tenant (public/shell/Celery).
    # / FK to the CONCRETE TibilletUser, not the TermUser proxy (its manager filters by
    # tenant and would break outside a tenant context).
    term_user = models.OneToOneField(
        "AuthBillet.TibilletUser", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="terminal",
        verbose_name=_("Compte du terminal"),
    )

    # --- Capacite « imprime » (NOUVEAU) ---
    # L'imprimante sur laquelle CE terminal sort ses tickets.
    # Plusieurs terminaux peuvent pointer la meme imprimante (un Pi vers une imprimante
    # cloud, un sunmi vers l'imprimante integree d'un autre sunmi).
    # / The printer this terminal prints on. Several terminals may share one printer.
    printer = models.ForeignKey(
        Printer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='terminaux',
        verbose_name=_("Imprimante"),
        help_text=_("Imprimante utilisee par ce terminal. Vide : pas d'impression."),
    )

    # --- Capacite « encaisse par carte » (deplacee depuis kiosk) ---
    registration_code, stripe_id, type, archived  # inchanges
    # + les methodes status() et get_stripe_id()
```

**Points de vigilance sur le code :**

- `laboutik/models.py` n'importe **ni `settings` ni `uuid4`**. La convention du fichier est
  `import uuid as uuid_module` (l.8) et `default=uuid_module.uuid4`. **Suivre la convention
  du fichier**, ne pas introduire `uuid4` nu.
- Placer la classe **après `Printer`** (qui finit l.346), puisqu'elle le référence en nom nu.
- Le `related_name="terminal"` est **conservé tel quel** — c'est celui de `kiosk.Terminal`,
  déjà utilisé par `kiosk/views.py:11`, `kiosk/views.py:106` et `wsocket/consumers.py:395`.
  On ne change pas l'accesseur, on déplace le modèle.

### Ce qui suit le déplacement

| Fichier | Changement |
|---|---|
| `kiosk/models.py:150` | `PaymentsIntent.terminal` → FK vers `"laboutik.Terminal"` |
| `kiosk/models.py:194` | `send_to_terminal(self, terminal: "Terminal")` → annotation |
| `kiosk/models.py:130-135` | **`Meta.verbose_name = "TPE Bancaire"` et `__str__`** → à renommer : un terminal générique sans TPE s'afficherait « TPE Bancaire / bbpos_wisepos_e Tablette Bar » |
| `kiosk/admin.py:26, 44, 90, 123` | `TerminalForm` / `TerminalAdmin` → déplacés (voir §5, le form est **bloquant**) |
| `kiosk/views.py:172, 228` | `getattr(request.user, "terminal", None)` — **l'accesseur ne change pas**, seul l'import bouge |
| `Administration/admin/dashboard.py:599` | `_safe_rev("staff_admin:kiosk_terminal_changelist")` → `laboutik_terminal_changelist`. **Lien mort sinon.** (l.606 `kiosk_paymentsintent_changelist` reste valide) |
| `Administration/management/commands/demo_data_v2.py:447` | `from kiosk.models import Terminal` → rebrancher |

**Aucun changement** dans `kiosk/tasks.py` ni `wsocket/consumers.py` : ils n'importent que
`PaymentsIntent`, qui reste dans `kiosk`. Vérifié.

**Pas de dépendance circulaire** : `laboutik` n'importe `kiosk` nulle part. Après le
chantier, `kiosk/models.py` importera `laboutik` — sens unique, sûr. Vérifié.

### Recette de migration — la plus simple, rien en production

Ni réécriture d'historique, ni `SeparateDatabaseAndState` (elle ne sert qu'à préserver des
données — il n'y en a pas). **Migrations linéaires auto-générées :**

1. Déplacer la classe, pointer `PaymentsIntent.terminal` sur `"laboutik.Terminal"`.
2. `makemigrations` génère :
   - `laboutik/0002` : `CreateModel Terminal` + `RemoveField pointdevente.printer`
   - `kiosk/0005` : `AlterField paymentsintent.terminal` + `DeleteModel Terminal`
   - La dépendance `kiosk/0005 → laboutik/0002` est posée automatiquement.

**Ne pas toucher à `kiosk/0002_terminal.py`, `0003`, `0004`.** Aucune migration d'une autre
app ne dépend de `kiosk` (vérifié). Les réécrire casserait les schémas dev existants
(`InconsistentMigrationHistory`, tables orphelines dans N schémas).

> ⚠️ **Piège** : les schémas **dev** contiennent des `kiosk_paymentsintent` qui pointent vers
> `kiosk_terminal`. L'`AlterField` vers la table `laboutik_terminal` (vide) **violera la
> nouvelle contrainte FK**. Ajouter un **`RunPython` de purge des `PaymentsIntent`** en tête
> de `kiosk/0005` — légitime, rien n'est en production.

### `laboutik.PointDeVente.printer` — **supprimé**

`laboutik/models.py:469`. LaBoutik V2 n'est pas en production : **aucune data migration**,
on supprime la colonne.

## 2. Résolution — une fonction, pas 20 accès inline

```python
# laboutik/views.py
def imprimante_du_terminal(user):
    """
    Renvoie l'imprimante ACTIVE du terminal courant, ou None.
    / Returns the current terminal's ACTIVE printer, or None.

    LOCALISATION : laboutik/views.py

    Renvoie None dans quatre cas, tous legitimes :
    - l'utilisateur n'est pas authentifie (chemin Api-Key V1 : AnonymousUser) ;
    - c'est un humain en session admin, pas un terminal (pas de .terminal) ;
    - le terminal n'a pas d'imprimante ;
    - l'imprimante est desactivee.

    Aucun de ces cas n'est une erreur : on n'imprime pas, c'est tout.
    """
    if not user or not user.is_authenticated:
        return None

    # getattr avec defaut FONCTIONNE sur un reverse OneToOne absent : Django leve
    # RelatedObjectDoesNotExist, qui herite d'AttributeError. Verifie.
    # / getattr with a default DOES work on a missing reverse OneToOne.
    terminal = getattr(user, 'terminal', None)
    if terminal is None:
        return None

    printer = terminal.printer
    if printer is None or not printer.active:
        return None

    return printer
```

**Garde indispensable** : `HasLaBoutikTerminalAccess` (`BaseBillet/permissions.py:86`) a un
fallback V1 où `request.user` peut être un `AnonymousUser` (header Api-Key) ou un humain en
session admin. Ne pas contourner cette fonction par un accès direct.

**Conséquence assumée** : une session humaine n'imprime plus le ticket client (voir
[SPEC §5](./SPEC.md#la-conséquence-assumée--plus-dimpression-en-session-humaine)).

## 3. Sites à basculer — recensement complet

### a) Lecteurs de `pv.printer` / `point_de_vente.printer` — `laboutik/views.py`

| Lignes | Ce qui s'imprime |
|---|---|
| 1766-1768 | `state["printer"]` → **l'abonnement WebSocket** (voir §4) |
| 2038, 2045 | Ticket Z (clôture) |
| 2239, 2281 | Ticket X (recap) |
| 4862, 4875 | Billet (`imprimer_billet`) |
| 5700-5701 | Auto-print billets, PV billetterie |
| 5885-5886 | Auto-print billets, second point d'appel |
| 8254, 8273 | Reçu « vider carte » |
| 8345, 8405 | Ticket de vente |

### b) `select_related("printer")` sur `PointDeVente` — **crash immédiat si oublié**

`laboutik/views.py:2225, 4930, 5591, 5767, 8253, 8332`.

Après suppression de la colonne, ces requêtes lèvent un **`FieldError` à la construction**,
avant même de lire `.printer`. Six sites, à retirer ou réorienter.

### c) Signature d'`imprimer_billet()`

`laboutik/views.py:4846` prend le PV en paramètre pour en tirer l'imprimante. **Changer la
signature** (recevoir l'imprimante, ou le user). Trois appelants :
`laboutik/views.py:5069, 5710, 5893`.

### d) Commande de seed dev

`laboutik/management/commands/create_test_pos_data.py` : sept sites
`"printer": imprimante_mock` dans les `defaults` de `PointDeVente.update_or_create`
(lignes **780, 795, 810, 836, 856, 907, 974**). L'imprimante mock est créée l.745-751.

→ La rattacher à un `Terminal` de test, pas au PV. **Sans ça, le seed dev casse.**

### e) Admin

`Administration/admin/laboutik.py:154` — champ `printer` dans les fieldsets du
**`PointDeVenteAdmin`**. À retirer.

### f) Vérifiés sans impact (ne rien toucher)

- `laboutik/archivage.py:302-330` lit `ImpressionLog.printer` — **champ distinct**
  (`laboutik/models.py:1083`), intouché.
- `tests/pytest/test_pos_vider_carte.py:395` asserte le toast « pas d'imprimante » : un admin
  en session n'aura pas de terminal → le toast sort toujours. **Test compatible.**
- Aucun template, cotton, serializer, api_v2 ou fixture ne lit `pv.printer`. Vérifié.
- Le reverse `Printer.points_de_vente` n'est utilisé nulle part.

## 4. Abonnement WebSocket — le cœur du symptôme

`laboutik/views.py:1765` injecte `state["printer"] = pv.printer`. C'est **cette ligne** qui
fait que 20 tablettes rejoignent le même groupe Redis.

```python
# AVANT — l'imprimante du PV : les N terminaux du PV s'abonnent au MEME groupe
state["printer"] = {"uuid": ..., "name": ...} if pv.printer else None

# APRES — l'imprimante de CE terminal
printer_du_terminal = imprimante_du_terminal(request.user)
state["printer"] = {
    # Le PK de Printer s'appelle `uuid`, PAS `id` (laboutik/models.py:263).
    "uuid": str(printer_du_terminal.uuid),
    "name": printer_du_terminal.name,
} if printer_du_terminal else None
```

**Côté JS : aucun changement de logique.** `state.printer` n'est lu qu'à un seul endroit,
`laboutik/static/js/manageSunmiPrint.js:135-136`, pour construire l'URL du WebSocket.

> ⚠️ Modifier **`laboutik/static/js/`**, jamais `www/static/js/` — ce dernier est le
> résultat de `collectstatic`, il est écrasé.

Le transport n'a **pas** besoin de changer : le groupe Redis est déjà indexé par l'UUID de
l'imprimante cible (`wsocket/consumers.py:209`, `laboutik/printing/sunmi_inner.py:194`).
Il était déjà correct — seul l'abonnement était faux.

Conséquence directe : le cas « le sunmi A imprime sur l'imprimante du sunmi B » marche sans
rien ajouter. `Terminal_A.printer` = l'imprimante Inner de B ; B est abonné à cette
imprimante parce que c'est la sienne ; A envoie dans le groupe, B imprime.

## 5. Admin

### `PointDeVenteAdmin` (`Administration/admin/laboutik.py:154`)

Retirer le champ `printer` des fieldsets.

### `TerminalAdmin` — déplacé depuis `kiosk/admin.py:123`

> ⚠️ **Deux pièges bloquants, à traiter AVANT de croire que ça marche.**
>
> **1. `TerminalForm.clean()` (`kiosk/admin.py:90-95`) rend un terminal sans TPE inéditable.**
> Le form exige un `registration_code` dès que `type == STRIPE_WISEPOS` et qu'il n'y a pas de
> `stripe_id` — or `type` a `default=STRIPE_WISEPOS`. Une tablette LaBoutik créée au claim
> (sans TPE) lèverait donc une `ValidationError` **à chaque édition**, et `_post_clean()`
> (l.97-121) appellerait `get_stripe_id()` → « The registration code is not set ».
> **Impossible de lui assigner une imprimante.**
> → Ne valider les champs TPE **que si un TPE est effectivement demandé**. Le `type` doit
> devenir nullable, ou gagner une valeur « pas de TPE ».
>
> **2. Le workflow admin passe de « créer » à « éditer ».**
> Aujourd'hui, l'admin **crée** un `Terminal` TPE et lui choisit une borne. Après le chantier,
> **le claim a déjà créé le `Terminal`** — en créer un second pour le même `term_user`
> violerait le OneToOne. Le geste devient : *éditer le Terminal existant* pour y saisir le
> `registration_code` (TPE) et/ou choisir l'imprimante.
> → Revoir `has_add_permission` (comme `TermUserAdmin.has_add_permission`, qui renvoie déjà
> `False` avec la même logique : « un TermUser naît uniquement d'un claim »).

- `list_display` : `name`, `printer`, le TPE, l'état actif (lu depuis `term_user.is_active`).
- Dropdown `printer` → table **tenant** : isolation physique, **aucun `formfield_for_foreignkey`
  à écrire**.
- **Action « Révoquer le terminal »** — le mécanisme manque aujourd'hui. Deux leviers, les
  **deux** sont nécessaires :
  - `terminal.term_user.is_active = False` → coupe le bridge et refuse les reconnexions WS ;
  - `terminal.term_user.laboutik_api_key.revoked = True` → coupe le header Api-Key. Sans ça,
    la clé stockée sur l'appareil permettrait de re-bridger si `is_active` était remis.

  ⚠️ Le reverse `laboutik_api_key` (`BaseBillet/models.py:2858`) **peut être absent** (clés V1
  sans user, et `term_user` est nullable). Garder l'action avec le même pattern `getattr`.

  (`claimed_at` n'est **pas** un levier : plus rien ne le lit après le claim.)

### `PrinterAdmin` (`Administration/admin/laboutik.py`)

Ajouter une colonne « Terminaux » en lecture seule (`printer.terminaux.all()`) pour voir qui
imprime dessus.

### `TermUserAdmin` (`Administration/admin_tenant.py:4901`)

`list_display` affiche `email`, qui est synthétique (`{uuid}@terminals.local`) — illisible.
Le nom lisible est dans `first_name` (posé au claim, `discovery/views.py:172`).
**Ajouter `first_name` à `list_display`.**

## 6. Création du `Terminal` au claim

Dans `_create_laboutik_terminal()` (`discovery/views.py:137`), qui tourne **déjà** dans un
`tenant_context` (ouvert `discovery/views.py:64`) — vérifié. Le `Terminal` s'écrit donc dans
le bon schéma.

```python
term_user = TermUser.objects.create(...)                            # existant
_key_obj, api_key_string = LaBoutikAPIKey.objects.create_key(...)   # existant

from laboutik.models import Terminal
Terminal.objects.create(
    name=pairing_device.name,
    term_user=term_user,
)
```

Le chemin Kiosque (`KI`) réutilise ce helper (`discovery/views.py:74-80`) : il hérite du
`Terminal` gratuitement — et ce sera **le même** objet que celui qui porte son TPE. Le chemin
Tireuse (`TI`) est **inchangé** dans ce chantier ; il est traité en
[CHANTIER-03](./CHANTIER-03-unification-appairage.md).

## 7. Tests

`tests/pytest/` — **lire `tests/PIEGES.md` avant d'écrire**.

- Le `Terminal` est créé au claim, dans le bon schéma tenant.
- `imprimante_du_terminal()` renvoie `None` pour un `AnonymousUser`, pour un humain en
  session admin, pour un terminal sans imprimante, et pour une imprimante inactive.
- **Le test qui prouve le fix** : deux terminaux opérant le **même point de vente**, avec deux
  imprimantes différentes → chacun reçoit **son** `state["printer"]`, pas celui de l'autre.
- Une imprimante partagée par deux terminaux → `printer.terminaux.count() == 2`.
- Révocation : après l'action admin, `is_active` est faux **et** la clé est révoquée.
- **Non-régression kiosk** : le TPE Stripe fonctionne toujours après le déplacement du modèle
  (`kiosk/views.py`, `PaymentsIntent`, `TerminalConsumer`).

### Tests existants à rebrancher (ils cassent à l'import)

| Fichier | Lignes |
|---|---|
| `tests/pytest/test_kiosk_models.py` | 14 (modèle), **112 et 138** (importent `TerminalForm` depuis `kiosk.admin`) |
| `tests/pytest/test_kiosk_flow.py` | 28 |
| `tests/pytest/test_kiosk_security.py` | 162 |

`tests/pytest/test_kiosk_branchements.py` n'importe pas `Terminal` — rien à faire.
`IsKioskTerminal` (`kiosk/views.py:53-83`) ne dépend **pas** du modèle (rôle +
`client_source_id`) — rien à faire.

Rappel piège multi-tenant : `schema_context()` pose un `FakeTenant`. `TermUser.save()` lit
`connection.tenant` → utiliser **`tenant_context()`**.

## 8. Signalements

- **i18n** : ce chantier ajoute des chaînes traduisibles (verbose_name, help_text, libellé
  de l'action admin). Les écrire en **français**. Le workflow `makemessages` est à lancer
  **par le mainteneur**.
- **Incohérence i18n préexistante à signaler, pas à corriger ici** : `laboutik/models.py`
  a ses msgid en anglais (`_("Accepts cash")`, l.440), alors que la règle du projet est le
  français. Hors périmètre.
- **CHANGELOG.md** + fiche dans `A TESTER et DOCUMENTER/` à créer en même temps que le code.
- **Vocabulaire** : `wsocket/consumers.py:256` définit un `TerminalConsumer` (le WebSocket du
  TPE kiosque), distinct du `PrinterConsumer`. Collision de vocabulaire à garder en tête.
