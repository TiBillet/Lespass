# USERS — Étiquettes sur les personnes, pour écrire à des groupes (Ghost)

> **Status :** spec du 2026-09-24, **non commencée**. Exploration : aucun code écrit.
> **Pré-requis :** aucun.
> **Origine :** spec bénévolat (`TODO/BENEVOLAT-planning-besoins.md`, décision D12).
> **Décisions :** D1 à D9 (§2.1) et P1 à P5 (§2.2), toutes tranchées. Aucune question ouverte.
> **Hors périmètre :** Brevo (D9), spec à part plus tard.

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
| Ghost | `send_to_ghost_email(email, name)` crée un membre avec les labels `"TiBillet"` + `"import <date>"`. Ne touche pas à un membre existant | `BaseBillet/tasks.py:1562` |
| Brevo | Clé d'API + bouton « tester ». **Aucune synchro de contacts.** SDK `sib-api-v3-sdk` installé | `BaseBillet/models.py:4688`, `admin_tenant.py:4184`, `pyproject.toml:51` |
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
| `name` | `CharField(50, unique)` | « Bénévole bar ». C'est aussi le nom du label Ghost et de la liste Brevo |
| `color` | `CharField(7, default="#0dcaf0")` | Même format que `Tag.color`. Recopier la validation `Tag._clean_hex` (`BaseBillet/models.py` ≈ l.138), pas de mixin |

Pas de lien avec `Tag` : la synchro des tags entre lieux (`admin_tenant.py:724`) ne voit
jamais ce catalogue.

### `EtiquetteUtilisateur` — qui porte quoi

| Champ | Type | Note |
|---|---|---|
| `etiquette` | FK `Etiquette`, `CASCADE`, `related_name="porteurs"` | Supprimer une étiquette la retire de tout le monde |
| `user` | FK `AUTH_USER_MODEL`, `CASCADE`, `related_name="etiquettes_du_lieu"` | P4 |
| `source` | `CharField(choices)` | `MANUELLE`, `BENEVOLAT`, `ADHESION` (P5, D5) |
| `created_at` | `DateTimeField(auto_now_add)` | |

`UniqueConstraint(fields=["etiquette", "user"])`.

**Piège multi-tenant.** `user.etiquettes_du_lieu` n'existe que dans un schéma de lieu.
Appelé depuis `public` (commande de gestion lancée sans `tenant_context`, tâche Celery mal
placée), il lève `relation "BaseBillet_etiquetteutilisateur" does not exist`. Toujours
passer par `EtiquetteUtilisateur.objects.filter(user=...)` dans un contexte de lieu.

Migration : une seule, dans `BaseBillet`, TENANT_APPS.

## 4. Admin

- **Fiche d'une personne** (`HumanUserAdmin`) : un inline « Étiquettes » (étiquette, source
  en lecture seule, date). Premier inline de cette fiche. À vérifier au chantier : un inline
  dont la FK pointe `TibilletUser` s'accroche-t-il à l'admin du **proxy** `HumanUser` ?
  (Django l'accepte si le modèle concret est dans la chaîne des parents du proxy.)
- **Liste des personnes** : un filtre par étiquette.
- **Action groupée** « Ajouter une étiquette » / « Retirer une étiquette » sur les personnes
  cochées. Écran intermédiaire par `get_urls()` (précédents : `module_toggle_modal`,
  `Administration/admin_tenant.py:513` ; `admin/module_page.html`, `dashboard.py:1503`).
- **Catalogue** (`EtiquetteAdmin`, nouveau) : nom, couleur, et une colonne « Personnes »
  (combien la portent), avec un lien vers la liste des personnes filtrée. Entrée de menu
  dans `Administration/admin/dashboard.py`, à côté des utilisateurs.

## 5. Étiquettes automatiques (D5)

| Événement | Étiquette posée | Retirée quand |
|---|---|---|
| Inscription à un besoin bénévole | l'`Etiquette` choisie sur la **tâche** (`TacheBenevole.etiquette`, FK `Etiquette` facultative, ajoutée à la spec bénévolat). Ex : tâche « Tenir le bar » → « Bénévole bar » | Jamais : on reste « bénévole bar » après son créneau |
| Adhésion validée | l'`Etiquette` choisie sur le **produit d'adhésion** (`Product.etiquette_adherent`, FK `Etiquette` facultative). Ex : « Adhérent·e » | Selon le choix de l'admin sur le même produit (D6) : `Product.etiquette_adherent_duree` = « tant que l'adhésion est valide » (défaut) ou « pour toujours » |

Les étiquettes automatiques ne sont posées que si le produit ou la tâche a une étiquette
choisie. Sans réglage, rien ne se passe.

**L'étiquette conditionnée (D6).** Avec « tant que l'adhésion est valide » :

- **Pose** : quand une adhésion à ce produit est validée (même moment que l'envoi actuel
  vers Ghost par `send_to_ghost`, `BaseBillet/tasks.py:1667`).
- **Retrait** : une tâche Celery quotidienne `retirer_les_etiquettes_d_adhesion_expirees`,
  même boucle sur les lieux que `membership_renewal_reminder` (`BaseBillet/tasks.py:1691`).
  Pour chaque étiquette de source `ADHESION` : si la personne n'a **plus aucune** adhésion
  valide (`deadline >= maintenant`) à un produit qui pose cette étiquette « tant que
  valide », on la retire.
- **Renouvellement** : la nouvelle adhésion validée repose l'étiquette.
- **Jamais retirée** si elle est de source `MANUELLE` (P5), ou si le produit dit « pour
  toujours ».

Une étiquette sans année (« Adhérent·e ») suffit donc : elle suit l'état réel. Avec « pour
toujours », nommer l'étiquette avec l'année (« Adhérent·e 2026 »).

## 6. Synchro vers Ghost (D7)

**Quand :** après chaque ajout ou retrait d'une `EtiquetteUtilisateur`, une tâche Celery
`synchroniser_etiquettes_ghost(user_pk)` part après la transaction
(`transaction.on_commit`). Un bouton admin « Tout resynchroniser » sert de filet.

**Quoi :** pour cette personne, dans Ghost :

1. Chercher le membre par email (même appel que `send_to_ghost_email`, `tasks.py` ≈ l.1601).
2. **Pas de membre : on le crée**, avec son nom et ses étiquettes en labels (D8), par le même
   appel que `send_to_ghost_email` aujourd'hui (création + labels `"TiBillet"`, `"import <date>"`).
   Il est abonné comme toute personne créée par le site.
3. Membre trouvé : labels voulus = labels actuels − (noms des `Etiquette` du lieu que la
   personne n'a plus) + (noms de ses étiquettes). Si ça change : `PUT /ghost/api/admin/members/{id}/`
   avec `{"members": [{"labels": [...]}]}`.

Le code Ghost (jeton JWT, recherche du membre, `PUT`) est aujourd'hui dans
`send_to_ghost_email`. Le chantier le range dans `newsletter/client_ghost.py`, qui porte
déjà `forger_token_ghost` (≈ l.54), pour que les deux tâches l'appellent. Les appels
actuels de `send_to_ghost_email` ne changent pas de comportement.

**Envoyer à un groupe, côté Ghost :** dans l'éditeur de Ghost, au moment d'envoyer une
lettre, on choisit les destinataires « membres avec le label *Bénévole bar* ». Rien à coder
côté Lespass pour ça.

## 7. Brevo : plus tard (D9)

Hors périmètre. Notes pour la future spec : Brevo n'a pas de labels mais des **listes**.
Une étiquette y deviendrait une liste `<nom du lieu> · <nom de l'étiquette>`, créée au
premier besoin (`ContactsApi.create_list`), avec `add_contact_to_list` /
`remove_contact_from_list`. Aujourd'hui, seuls la clé (`BrevoConfig`) et le bouton « tester »
existent ; le SDK `sib-api-v3-sdk` est installé. Même règle qu'en D8 pour un contact absent.

## 8. Tests

| Quoi | Où |
|---|---|
| `Etiquette` : nom unique, couleur nettoyée ; unicité (étiquette, personne) ; manuelle l'emporte sur automatique (P5) ; `CASCADE` | `tests/pytest/test_etiquettes_modele.py` |
| Deux lieux : la même personne, des étiquettes différentes, aucune fuite de l'un à l'autre | idem |
| Inscription bénévole avec `TacheBenevole.etiquette` → étiquette posée ; sans → rien | `tests/pytest/test_etiquettes_automatiques.py` |
| Adhésion validée avec `Product.etiquette_adherent` → posée ; « tant que valide » + expiration → retirée ; renouvellement → reposée ; « pour toujours » → jamais retirée ; source manuelle → jamais retirée ; deux adhésions dont une encore valide → gardée | idem |
| Ghost : membre inexistant → créé avec ses labels ; membre existant → `PUT` avec les bons labels ; labels hors catalogue `Etiquette` jamais retirés (P2) ; rien de changé → aucun `PUT` (Ghost mocké) | `tests/pytest/test_etiquettes_ghost.py` |
| `send_to_ghost_email` : même comportement qu'avant (non-régression) | idem |
| Admin : inline sur la fiche, filtre, action groupée, catalogue avec colonne « Personnes » | test admin |
| « Synchroniser les tags » ne touche pas au catalogue `Etiquette` | idem |

Chaque test vu **échouer** sur une mutation volontaire avant d'être livré.

## 9. Questions ouvertes

Aucune. Questions tranchées le 2026-09-24 (D4 à D9), propositions P1 à P5 validées le 2026-09-25.

Avant de coder : une relecture par un agent Fable (exactitude face au code, pièges
techniques), comme pour la spec bénévolat.

## 10. Découpage proposé

| Chantier | Contenu |
|---|---|
| 1 | Modèles `Etiquette` + `EtiquetteUtilisateur` + admin (catalogue, inline, filtre, action groupée) |
| 2 | Étiquettes automatiques (bénévolat, adhésion, retrait à l'expiration) |
| 3 | Synchro Ghost (client dans `newsletter/client_ghost.py`, tâche, bouton « Tout resynchroniser ») |

Chaque chantier : son fichier `CHANGELOG/YYYY-MM-DD-slug.md`. Chaînes en français (`_()`),
à signaler au mainteneur pour le workflow i18n.
