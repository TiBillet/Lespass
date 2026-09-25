# USERS — Étiquettes sur les personnes, pour écrire à des groupes (Ghost)

> **Status :** spec du 2026-09-24, **non commencée**. Exploration : aucun code écrit.
> **Pré-requis :** aucun.
> **Origine :** spec bénévolat (`TODO/BENEVOLAT-planning-besoins.md`, décision D12).
> **Décisions :** D1 à D9 (§2.1) et P1 à P5 (§2.2), toutes tranchées. Aucune question ouverte.
> **Hors périmètre :** Brevo (D9), spec à part plus tard.
> **Relue** le 2026-09-25 par un agent Fable (exactitude face au code, faisabilité) ; ses
> corrections sont intégrées.

## Lexique

| Terme | Sens |
|---|---|
| Étiquette | un nom (et une couleur) du catalogue `Etiquette` du lieu, posé sur une personne. Ex : « Bénévole bar », « Adhérent·e 2026 ». **Distinct des `Tag`** des événements (D4) |
| Personne | un `TibilletUser`, vu depuis un lieu. Le même compte sert dans tous les lieux |
| Lieu | un tenant (un schéma PostgreSQL) |
| Étiquette manuelle | posée à la main par l'admin du lieu |
| Étiquette automatique | posée par le site lors d'un événement (inscription bénévole, adhésion) |
| Ghost | l'outil de lettre d'information du lieu. Il range ses membres avec des **labels** |
| Brevo | un autre outil d'emailing. Il range ses contacts dans des **listes** |
| Synchro | recopier les étiquettes d'une personne vers Ghost ou Brevo. Toujours dans ce sens-là |

## 1. Pourquoi ce chantier

Le mainteneur, le 2026-09-23 : « on a aucune étiquette sur les users aujourd'hui. C'est un
manque ». Le but : **envoyer des mails à des groupes précis** (« seulement les bénévoles
bar », « seulement les adhérent·es ») depuis Ghost ou Brevo.

Ce qui existe :

| Brique | État | Où |
|---|---|---|
| `Tag` | Nom, slug, couleur. Posé sur événements, produits, initiatives (`crowds`), filtres de fédération. **Rien sur les personnes** | `BaseBillet/models.py:132` |
| Synchro des tags entre lieux | Action admin « Synchroniser les tags » : recopie les **noms** et couleurs des tags des lieux fédérés | `Administration/admin_tenant.py:724` |
| Ghost | `send_to_ghost_email(email, name)` crée un membre avec les labels `"TiBillet"` + `"import <date>"`. Ne touche pas à un membre existant. Appelée à l'adhésion par `send_to_ghost`, **seulement si `membership.newsletter`** (`BaseBillet/triggers.py:285`) | `BaseBillet/tasks.py:1562`, `1667` |
| Brevo | Clé d'API + bouton « tester » + **création du contact à l'adhésion** (`send_to_brevo`, si `membership.newsletter`). **Aucune liste.** SDK `sib-api-v3-sdk` installé | `BaseBillet/models.py:4688`, `BaseBillet/tasks.py:1522`, `admin_tenant.py:4184`, `pyproject.toml:51` |
| Consentement newsletter | `TibilletUser.accept_newsletter` vaut `True` par défaut et n'est jamais demandé : **ce n'est pas un consentement** | `AuthBillet/models.py:140` |
| Fiche personne en admin | `HumanUserAdmin`, sans inline | `Administration/admin_tenant.py:1066` |

**La contrainte d'architecture.** `TibilletUser` est dans le schéma `public`, commun à tous
les lieux. Le catalogue d'étiquettes est dans le schéma de chaque lieu. On ne peut donc pas
mettre un champ `etiquettes` sur l'utilisateur. La liaison vit **dans le schéma du lieu**, et pointe vers
l'utilisateur de `public` : c'est le même motif que `Membership.user` ou `Booking.user`.
Conséquence voulue : chaque lieu a ses propres étiquettes sur les mêmes personnes.

## 2. Décisions

### 2.1 Tranchées par le mainteneur

| # | Sujet | Décision |
|---|---|---|
| D1 | Où l'écrire | Une spec à part, celle-ci (2026-09-23). |
| D2 | Pour qui | Des étiquettes sur les utilisateurs, les bénévoles et les adhérent·es (2026-09-23). |
| D3 | Pour quoi faire | Écrire à des groupes précis via Ghost **ou** Brevo (2026-09-23). |
| D4 | Catalogue | **Un catalogue à part**, `Etiquette`, réservé aux personnes. On ne réutilise pas `Tag` : rien de mélangé avec les tags d'événements, et rien de recopié vers les lieux fédérés par « Synchroniser les tags » (2026-09-24, ex-Q1). |
| D5 | Étiquettes automatiques | **Bénévolat et adhésions**, chacun seulement si l'admin a choisi une étiquette sur la tâche ou sur le produit d'adhésion (§5). La pose à la main reste toujours possible (2026-09-24, ex-Q2). |
| D6 | Étiquette d'adhésion à l'expiration | **Étiquette conditionnée, au choix de l'admin** sur le produit d'adhésion : « tant que l'adhésion est valide » (retirée à l'expiration, reposée au renouvellement) ou « pour toujours » (§5). Une étiquette posée à la main n'est jamais retirée automatiquement (2026-09-24, ex-Q3). |
| D7 | Moment de la synchro | **À chaque changement** (tâche Celery après la transaction), plus un bouton « Tout resynchroniser » en secours (2026-09-24, ex-Q4). |
| D8 | Personne étiquetée, pas encore dans Ghost/Brevo | **On la crée et on l'abonne**, comme le reste du site (même choix que la lettre du bénévolat). Limite connue et acceptée : étiqueter une personne l'abonne à la lettre sans qu'elle l'ait demandé ; `accept_newsletter` n'est pas consulté (2026-09-24, ex-Q5). |
| D9 | Brevo | **Ghost d'abord.** Ce chantier livre les étiquettes et la synchro Ghost. Brevo fera l'objet d'une spec à part, quand un lieu en aura besoin (2026-09-24, ex-Q6). |

### 2.2 Proposées par cette spec, validées par le mainteneur (2026-09-25)

| # | Sujet | Proposition | Pourquoi |
|---|---|---|---|
| P1 | Sens de la synchro | **Lespass → Ghost seulement.** On ne relit jamais les labels de Ghost. | Une seule source de vérité. Pas de conflit à arbitrer. |
| P2 | Labels touchés dans Ghost | La synchro ne retire que les labels **qui portent le nom d'une `Etiquette` du lieu**. Les autres labels (`"TiBillet"`, `"import <date>"`, ceux posés à la main dans Ghost) ne sont jamais retirés. | L'équipe peut garder ses propres labels dans Ghost. |
| P3 | Qui voit les étiquettes | **L'admin du lieu seulement.** Jamais sur le site public, ni dans « Mon compte » en V1. | « Bénévole bar » est une donnée sur la personne. Pas besoin de l'afficher. |
| P4 | Suppression d'une personne | Ses étiquettes partent avec elle (`CASCADE`). | Une étiquette sans personne ne veut rien dire. |
| P5 | Étiquette manuelle + automatique | Une seule ligne par couple (étiquette, personne). Si l'admin pose à la main une étiquette déjà automatique, elle devient manuelle. Un retrait automatique ne touche jamais une étiquette manuelle. | Le choix de l'admin l'emporte sur la machine. |

## 3. Modèle de données (`BaseBillet/models.py`)

```
Etiquette ──< EtiquetteUtilisateur >── TibilletUser (schéma public)
```

### `Etiquette` — le catalogue du lieu (D4)

| Champ | Type | Note |
|---|---|---|
| `name` | `CharField(50, unique)` | « Bénévole bar ». C'est aussi le nom du label Ghost. **En lecture seule après création** (`get_readonly_fields`) : renommer laisserait l'ancien label chez tous les membres Ghost, et P2 ne saurait plus le retirer. Pour renommer : créer la nouvelle, la poser, supprimer l'ancienne |
| `color` | `CharField(7, default="#0dcaf0")` | Même format que `Tag.color`. Recopier la validation `Tag._clean_hex` (`BaseBillet/models.py:137`), pas de mixin |

Pas de lien avec `Tag` : la synchro des tags entre lieux (`admin_tenant.py:724`) fait du SQL
brut sur `BaseBillet_tag`, elle ne voit jamais ce catalogue. Déclarer `Etiquette` **avant**
`Product` dans `models.py` (≈ l.1175), ou la référencer par la chaîne `"Etiquette"`.

### `EtiquetteUtilisateur` — qui porte quoi

| Champ | Type | Note |
|---|---|---|
| `etiquette` | FK `Etiquette`, `CASCADE`, `related_name="porteurs"` | Supprimer une étiquette la retire de tout le monde |
| `user` | FK `AUTH_USER_MODEL`, `CASCADE`, `related_name="etiquettes_du_lieu"` | P4 |
| `source` | `CharField(choices)` | `MANUELLE`, `BENEVOLAT`, `ADHESION` (P5, D5) |
| `created_at` | `DateTimeField(auto_now_add)` | |

`UniqueConstraint(fields=["etiquette", "user"])`.

**Toute pose (manuelle ou automatique) ajoute le lieu à `user.client_achat`** s'il n'y est
pas (même geste que `BaseBillet/triggers.py:272-274`). Sans ça, une personne étiquetée qui
n'a rien acheté ici (un bénévole) serait invisible dans l'admin : `HumanUserManager` ne
montre que les comptes dont `client_achat` contient le lieu (`AuthBillet/models.py:416-422`).

**Piège multi-tenant.** `user.etiquettes_du_lieu` n'existe que dans un schéma de lieu.
Appelé depuis `public` (commande de gestion lancée sans `tenant_context`, tâche Celery mal
placée), il lève `relation "BaseBillet_etiquetteutilisateur" does not exist`. Toujours
passer par `EtiquetteUtilisateur.objects.filter(user=...)` dans un contexte de lieu.

Migrations : une par chantier, dans `BaseBillet` (TENANT_APPS). Chantier 1 : les deux
modèles. Chantier 2 : les deux champs de `Product` (§5).

## 4. Admin

- **Fiche d'une personne** (`HumanUserAdmin`) : un inline « Étiquettes » (étiquette, source
  en lecture seule, date). Faisable sur le proxy `HumanUser` : Django 4.2 accepte une FK vers
  le modèle concret du proxy (`django/forms/models.py`, `_get_foreign_key`). Précédent :
  `MembershipPriceInline` sur `MembershipProductAdmin` (`Administration/admin/products.py:1397`).
- **Liste des personnes** : `list_filter = ["etiquettes_du_lieu__etiquette"]` (relation
  inverse `public` → lieu ; précédent `UserWithMembershipValid`, `admin_tenant.py:937-980`).
- **Action groupée** « Étiqueter… » sur les personnes cochées : une action Django standard
  `(self, request, queryset)` qui affiche elle-même un petit formulaire (l'étiquette, ajouter
  ou retirer), puis applique au second envoi. Pas de `get_urls()`, pas de modale. Précédent :
  `approuver_propositions` (`admin_tenant.py:2518`, signature l.2815).
- **Catalogue** (`EtiquetteAdmin`, nouveau) : nom, couleur, et une colonne « Personnes »
  (combien la portent), avec un lien vers la liste des personnes filtrée. Dans
  `Administration/admin/dashboard.py` : l'entrée de menu (≈ l.196) **et** les deux
  dictionnaires par modèle, aide (≈ l.1316-1321) et verbe (≈ l.1387-1389), avec la clé
  `"BaseBillet.etiquette"`.
- **Champs d'adhésion** (`Product.etiquette_adherent`, `etiquette_adherent_duree`) : visibles
  seulement dans `MembershipProductAdmin`. Il hérite des `fieldsets` de `ProductAdmin`
  (`Administration/admin/products.py:983`), partagés avec billets, ressources, caisse et fûts :
  lui donner ses propres `fieldsets` (ou un `get_fieldsets`).

## 5. Étiquettes automatiques (D5)

| Événement | Étiquette posée | Retirée quand |
|---|---|---|
| Inscription à un besoin bénévole | l'`Etiquette` choisie sur la **tâche** (`TacheBenevole.etiquette`, FK `Etiquette`, `null`, `SET_NULL`, ajoutée à la spec bénévolat). Ex : tâche « Tenir le bar » → « Bénévole bar » | Jamais : on reste « bénévole bar » après son créneau |
| Adhésion validée | l'`Etiquette` choisie sur le **produit d'adhésion** (`Product.etiquette_adherent`, FK `Etiquette`, `null`, `SET_NULL`). Ex : « Adhérent·e » | Selon le choix de l'admin sur le même produit (D6) : `Product.etiquette_adherent_duree` = « tant que l'adhésion est valide » (défaut) ou « pour toujours » |

Les étiquettes automatiques ne sont posées que si le produit ou la tâche a une étiquette
choisie. Sans réglage, rien ne se passe.

**L'étiquette conditionnée (D6).** Avec « tant que l'adhésion est valide » :

- **Pose** : au moment où la date de fin de l'adhésion est posée, dans
  `Membership.set_deadline()` (`BaseBillet/models.py:4113`). C'est le seul point par lequel
  passent **tous** les chemins de validation : paiement (`triggers.py:267`), panier gratuit
  (`services_commande.py:500`), API (`validators.py:1134`), caisse (`laboutik/views.py:4899`
  et `4914`). **Ne pas** s'accrocher à `send_to_ghost` : il dépend de la case
  `membership.newsletter`, et la caisse ne le déclenche jamais (ses lignes sont `VALID`,
  jamais `PAID`). Si `membership.user` est vide (`SET_NULL`), ne rien poser.
- **Retrait** : une tâche Celery quotidienne `retirer_les_etiquettes_d_adhesion_expirees`,
  même boucle sur les lieux que `membership_renewal_reminder` (`BaseBillet/tasks.py:1691`),
  **lancée au même endroit qu'elle** : la commande `cron_morning`
  (`Administration/management/commands/cron_morning.py:90-102`), pas le beat de
  `TiBillet/celery.py`. Règle, en entier :
  - on ne regarde que les lignes de source `ADHESION` (jamais `MANUELLE` ni `BENEVOLAT`) ;
  - on garde l'étiquette si la personne a **au moins une** adhésion `is_valid()`
    (`BaseBillet/models.py:4252`, qui compte aussi les annulations) à un produit qui pose
    cette étiquette ;
  - on la garde aussi si **une** adhésion, valide ou non, pointe un produit qui la pose
    « pour toujours » ;
  - sinon, on la retire.
- **Renouvellement** : la nouvelle adhésion repasse par `set_deadline()` et repose
  l'étiquette.

Une étiquette sans année (« Adhérent·e ») suffit donc : elle suit l'état réel. Avec « pour
toujours », nommer l'étiquette avec l'année (« Adhérent·e 2026 »).

## 6. Synchro vers Ghost (D7)

**Quand :** après chaque ajout ou retrait, une tâche Celery
`synchroniser_etiquettes_ghost(user_pk)` part après la transaction. **Appels explicites, pas de
signal** : `transaction.on_commit(lambda: synchroniser_etiquettes_ghost.delay(user.pk))` aux
quatre endroits qui écrivent (inline admin, action groupée, pose automatique, retrait
nocturne). Un signal `post_save` ne verrait pas les `bulk_create` / `update`. Le schéma du lieu
suit la tâche : `tenant_schemas_celery` le met dans les en-têtes Celery. Un bouton admin
« Tout resynchroniser » sert de filet.

**Quoi :** pour cette personne, dans Ghost :

1. Chercher le membre par email.
2. **Pas de membre : on le crée**, avec son nom et ses étiquettes en labels (D8). Il est
   abonné comme toute personne créée par le site.
3. Membre trouvé : labels voulus = labels actuels − (noms des `Etiquette` du lieu que la
   personne n'a plus) + (noms de ses étiquettes). Si ça change :
   `PUT /ghost/api/admin/members/{id}/` avec `{"members": [{"labels": [...]}]}`.
   **Forme des labels : des objets.** Ghost renvoie des objets `{id, name, slug, …}` au GET ;
   on renvoie ces objets tels quels pour les labels gardés, plus `{"name": nom}` pour chaque
   étiquette ajoutée. (Le code actuel envoie des chaînes à la création,
   `BaseBillet/tasks.py:1617` : ne pas mélanger les deux formes dans un même `PUT`.)
4. Écrire le résultat dans `GhostConfig.ghost_last_log`, comme `send_to_ghost_email`
   (`tasks.py:1651-1658`) : c'est ce que lit l'admin quand « Tout resynchroniser » échoue.

**Où ranger le code.** `send_to_ghost_email` n'est **pas modifiée**. Une seule fonction
nouvelle dans `newsletter/client_ghost.py`, à côté de `forger_token_ghost` (≈ l.54) :
`synchroniser_labels_membre(url, cle, email, nom, labels_voulus, noms_du_catalogue)`
(GET, POST si absent, PUT si différent). Pas de non-régression à prouver : rien d'existant
ne bouge.

**Limite connue :** aujourd'hui, aucun `PUT` n'existe dans le projet. Que le `PUT` avec
`labels` **remplace** toute la liste ne se prouve qu'avec une vraie instance Ghost : test
manuel à faire une fois (§8).

**Lien avec la spec bénévolat.** Sa §5.8 pose le label « Bénévolat » par la lettre
d'information. Si ce chantier-ci est livré avant, §5.8 appelle `synchroniser_labels_membre`
au lieu de modifier `send_to_ghost_email`. Attention à une collision : si un lieu crée aussi
une `Etiquette` nommée « Bénévolat », P2 retirera ce label, à la prochaine synchro, aux
personnes qui ne portent pas l'étiquette dans Lespass. Règle : la lettre du bénévolat pose
alors l'`Etiquette` « Bénévolat » (créée si absente) sur la personne connectée, au lieu d'un
label en dur.

**Envoyer à un groupe, côté Ghost :** dans l'éditeur de Ghost, au moment d'envoyer une
lettre, on choisit les destinataires « membres avec le label *Bénévole bar* ». Rien à coder
côté Lespass pour ça.

## 7. Brevo : plus tard (D9)

Hors périmètre. Notes pour la future spec : Brevo n'a pas de labels mais des **listes**.
Une étiquette y deviendrait une liste `<nom du lieu> · <nom de l'étiquette>`, créée au
premier besoin (`ContactsApi.create_list`), avec `add_contact_to_list` /
`remove_contact_from_list`. Aujourd'hui existent la clé (`BrevoConfig`), le bouton « tester » et
`send_to_brevo` (`BaseBillet/tasks.py:1522`), qui crée le contact à l'adhésion si
`membership.newsletter`. Il manque les listes. Le SDK `sib-api-v3-sdk` est installé. Même règle qu'en D8 pour un contact absent.

## 8. Tests

| Quoi | Où |
|---|---|
| `Etiquette` : nom unique, couleur nettoyée ; unicité (étiquette, personne) ; manuelle l'emporte sur automatique (P5) ; `CASCADE` | `tests/pytest/test_etiquettes_modele.py` |
| Deux lieux : la même personne, des étiquettes différentes, aucune fuite de l'un à l'autre | idem |
| Inscription bénévole avec `TacheBenevole.etiquette` → étiquette posée ; sans → rien | `tests/pytest/test_etiquettes_automatiques.py` |
| Adhésion validée avec `Product.etiquette_adherent` → posée ; « tant que valide » + expiration → retirée ; renouvellement → reposée ; « pour toujours » → jamais retirée ; source manuelle → jamais retirée ; deux adhésions dont une encore valide → gardée | idem |
| Ghost : membre inexistant → créé avec ses labels ; membre existant → `PUT` avec les bons labels, en objets ; labels hors catalogue `Etiquette` jamais retirés (P2) ; rien de changé → aucun `PUT` ; `ghost_last_log` écrit (Ghost mocké par `unittest.mock.patch("newsletter.client_ghost.requests...")`, comme `tests/pytest/test_newsletter_ghost.py`) | `tests/pytest/test_etiquettes_ghost.py` |
| La tâche est lancée après la transaction (`captureOnCommitCallbacks`, ou tâche mockée : voir `tests/PIEGES.md` 9.45) | idem |
| Pose d'une étiquette → le lieu est ajouté à `user.client_achat` ; la personne apparaît dans la liste admin | `tests/pytest/test_etiquettes_modele.py` |
| Adhésion validée par la **caisse** (`laboutik`) → étiquette posée (chemin sans `trigger_A`) ; adhésion sans `user` → rien | `tests/pytest/test_etiquettes_automatiques.py` |
| Retrait nocturne : adhésion annulée par l'admin (`is_valid()` faux, deadline future) → retirée ; même étiquette posée « pour toujours » par un autre produit → gardée ; source `BENEVOLAT` → gardée | idem |
| Admin : inline sur la fiche, filtre, action groupée (formulaire puis application), catalogue avec colonne « Personnes », nom en lecture seule après création, champs d'adhésion visibles seulement sur les produits d'adhésion | `tests/pytest/test_etiquettes_admin.py` (client Django, pas Playwright) |
| **Test manuel**, une fois, sur une vraie instance Ghost : le `PUT` remplace bien la liste des labels | fiche CHANGELOG du chantier 3 |

Chaque test vu **échouer** sur une mutation volontaire avant d'être livré.

## 9. Questions ouvertes

Aucune. Questions tranchées le 2026-09-24 (D4 à D9), propositions P1 à P5 validées le 2026-09-25.

RGPD : le projet n'a ni export des données d'une personne, ni suppression de compte à
compléter (rien n'existe). Les étiquettes n'en ajoutent pas.

## 10. Découpage proposé

| Chantier | Contenu |
|---|---|
| 1 | Modèles `Etiquette` + `EtiquetteUtilisateur` + admin (catalogue, inline, filtre, action groupée) |
| 2 | Étiquettes automatiques : champs de `Product` + admin des produits d'adhésion, pose dans `set_deadline()`, pose bénévolat, retrait nocturne dans `cron_morning` |
| 3 | Synchro Ghost (`synchroniser_labels_membre` dans `newsletter/client_ghost.py`, tâche, bouton « Tout resynchroniser », test manuel) |

Chaque chantier : son fichier `CHANGELOG/YYYY-MM-DD-slug.md`. Chaînes en français (`_()`),
à signaler au mainteneur pour le workflow i18n.
