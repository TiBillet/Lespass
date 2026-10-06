# 15 — Spec : le verrou de moteur — les lieux existants restent sur l'ancien Fedow

**Date :** 2026-10-06
**Statut :** spec à implémenter. Décisions du mainteneur prises (§2).
**Hub :** `TECH_DOC/SESSIONS/FEDOW_IMPORT/` — décision S6 « hybride additif » (INDEX.md).

---

## 1. Le problème

La décision S6 dit : les lieux existants restent sur le Fedow distant (`fedow_connect`,
`fedow_public`), les nouveaux lieux utilisent le moteur local (`fedow_core`). Mais **rien
dans le code n'empêche un lieu existant de basculer** vers le moteur V2. Constat du
2026-10-06 :

1. **`module_toggle` ne vérifie rien** (`Administration/admin_tenant.py:608`). Tout admin de
   lieu peut activer `module_monnaie_locale`, `module_caisse`, `module_kiosk`,
   `module_tireuse`. Seul l'interrupteur « Caisse » est caché pour un lieu LaBoutik V1, et un
   POST direct passe quand même. Activer la caisse active aussi la monnaie locale
   (`admin_tenant.py:627-628`).
2. **L'admin `fedow_core` est ouvert par son URL à tout admin de lieu**, module actif ou non :
   `AssetAdmin`, `TokenAdmin`, `TransactionAdmin`, `FederationAdmin`
   (`fedow_core/admin.py:97, 500, 572, 686`) n'ont pour permission que
   `TenantAdminPermissionWithRequest`. Un admin de CLAF peut créer un asset V2 en tapant
   `/admin/fedow_core/asset/add/`.
3. **Un lieu V2 peut inviter n'importe quel lieu dans une fédération V2**, y compris CLAF ou un
   lieu fédéré avec lui (`pending_invitations`, autocomplétion sur `TenantAdmin`,
   `admin_tenant.py:5519`). L'invité accepte par l'URL (`accept_asset_invitation`,
   `fedow_core/admin.py` ~l.418). C'est le chemin de bascule le plus probable.
4. **Les drapeaux de module ne protègent presque rien.** Seul `module_caisse` garde la caisse
   V2 (`BaseBillet/permissions.py:112`). Le kiosk (`kiosk/views.py` `IsKioskTerminal`) et la
   tireuse (`controlvanne/permissions.py` `HasTireuseAccess`) ne lisent pas leur drapeau :
   seules les clés des terminaux appairés les protègent.
5. **Rien en base ne distingue un lieu legacy d'un lieu V2 neuf.** Le wizard crée les lieux
   sans aucun module V2. « Être V2 » n'existe que par un interrupteur.

Le réseau CLAF n'a **pas** de LaBoutik V1 (`server_cashless` vide) : `server_cashless` ne peut
donc pas servir de critère. Ses assets sont fédérés, et les lieux fédérés avec lui sont dans
le même cas.

## 2. Décisions du mainteneur (2026-10-06)

1. **Tous les lieux qui existent avant le déploiement restent en legacy**, côté moteur comme
   côté admin. Pas de règle d'arrêt, pas de décision au cas par cas : c'est le cas de
   pratiquement toute la prod.
2. **Un lieu créé après le déploiement démarre en V2.**
3. La bascule d'un lieu existant legacy → V2 n'est **pas** pour tout de suite et **n'est pas
   dans ce chantier** (aucun outil de bascule à écrire). Un gestionnaire de lieu ne peut
   jamais changer son moteur.
4. **Le lien « Assets » de l'admin legacy revient en accès direct** dans le menu latéral des
   lieux legacy (un clic, comme sur `main`).
5. Hors périmètre, déjà accepté comme attendu : adhésions plus poussées vers Fedow, ventes
   QR/NFC plus envoyées à LaBoutik V1, historique des ventes masqué avant la reprise R.

## 3. Le champ : `Client.moteur_monnaie`

**Fichier :** `Customers/models.py` — sur `Client` (SHARED_APPS, schéma `public`).

```python
# Moteur de monnaie du lieu. Un lieu LEGACY utilise l'ancien Fedow (fedow_connect) :
# les modules V2 et l'admin fedow_core lui sont fermes. Un lieu V2 utilise fedow_core.
# Le lieu ne change jamais cette valeur lui-meme : elle n'est dans aucun formulaire du lieu.
# / Venue currency engine. LEGACY = old Fedow; V2 modules and fedow_core admin closed.
MOTEUR_LEGACY, MOTEUR_V2 = 'legacy', 'v2'
MOTEUR_CHOICES = [
    (MOTEUR_LEGACY, _("Ancien Fedow")),
    (MOTEUR_V2, _("Moteur V2")),
]
moteur_monnaie = models.CharField(
    max_length=6, choices=MOTEUR_CHOICES, default=MOTEUR_V2,
    verbose_name=_("Moteur de monnaie"),
)
```

**Pourquoi sur `Client` et pas sur `Configuration` :**
- un lieu doit lire le moteur des **autres** lieux (filtrer les invitations V2) : `Client` est
  dans le schéma public, `Configuration` dans le schéma de chaque lieu ;
- un gestionnaire de lieu ne peut pas modifier le moteur : `moteur_monnaie` n'est dans
  aucun écran (ni admin du lieu, ni admin racine). Le moteur ne change que par la base
  (migrations `0006` / `0227`, ou une écriture directe) ;
- dans le code d'un lieu, la lecture ne coûte rien : `connection.tenant.moteur_monnaie`.

## 4. Les migrations

Aucune commande à écrire, aucune étape manuelle : deux migrations suffisent.

### 4.1 `Customers/migrations/0006_moteur_de_monnaie.py` (schéma public)

Dernière migration existante : `0005_libelles_fr_du_lieu`. Trois opérations, dans cet ordre :

1. `AddField(moteur_monnaie, default='legacy')` → **toutes les lignes existantes** reçoivent
   `legacy`.
2. `RunPython` : les `Client` de catégorie `WAITING_CONFIG` passent en `v2`. Ce sont les
   emplacements vides du pool (`create_empty_tenant`, `onboard/tasks.py:269-295`) : créés
   avant le déploiement, mais ils deviendront des lieux **créés après**. Le wizard les
   recatégorise (`WAITING_CONFIG` → `SALLE_SPECTACLE`) sans toucher au moteur.
   `reverse_code=migrations.RunPython.noop`.
3. `AlterField(moteur_monnaie, default='v2')` → tout `Client` créé ensuite (pool, wizard,
   tests) est en `v2`.

### 4.2 `BaseBillet/migrations/0227_moteur_v2_si_un_module_v2_est_actif.py` (chaque lieu)

Dépend de `('Customers', '0006_moteur_de_monnaie')` et de la dernière migration BaseBillet
(`0226_retirer_le_skin_de_la_configuration`).

`RunPython`, exécuté dans le schéma de chaque lieu :
- sortir tout de suite si le schéma est `public` (patron de migration de données du projet ;
  redondant avec le routeur de django-tenants, qui n'exécute pas BaseBillet dans `public`,
  mais inoffensif) ;
- lire la `Configuration` du lieu avec `apps.get_model('BaseBillet', 'Configuration')` puis
  **`Configuration.objects.first()`** (pas de `get_solo()` sur un modèle historique) ; **s'il
  n'y en a pas** (schéma d'un lieu neuf), ne rien faire : le `Client` est déjà en `v2` ;
- si **un** des drapeaux `module_caisse`, `module_monnaie_locale`, `module_kiosk`,
  `module_tireuse` est vrai : passer le `Client` de ce schéma en `v2` avec
  **`apps.get_model('Customers', 'Client').objects.filter(schema_name=connection.schema_name).update(moteur_monnaie='v2')`**
  (pas de `save()` : le modèle historique n'a pas `TenantMixin.save`). La table
  `Customers_client` est atteinte par le `search_path` (lieu, puis public), comme
  `laboutik/0002` lit `fedow_core_asset` ;
- **journaliser** chaque lieu basculé : `print(f"  -> [{schema}] moteur v2 (module V2 actif)")` ;
- sinon : ne rien faire, le lieu reste `legacy`.
- `reverse_code=migrations.RunPython.noop`.

`migrate_schemas` migre `public` d'abord, puis chaque lieu : `Customers 0006` est donc
toujours passée quand `0227` s'exécute. La dépendance d'une migration de lieu vers une app
partagée a des précédents (`laboutik/0002` → `fedow_core 0001`). Avec
`--executor=multiprocessing`, chaque processus met à jour sa propre ligne : pas de conflit.

**Pourquoi ce critère.** Un lieu qui a déjà un module V2 actif utilise déjà le moteur V2 :
le passer en `legacy` lui fermerait sa caisse et ses monnaies. Un lieu qui n'en a aucun
n'utilise que l'ancien Fedow.

**Ce que ça donne :**

| Où | Résultat attendu |
|---|---|
| **prod** | **hypothèse** : sur `main`, `module_caisse`, `module_monnaie_locale`, `module_tireuse` existent (depuis `BaseBillet/0204`) mais sont commentés dans `MODULE_FIELDS` : aucun interrupteur, le toggle répond 400. Ils devraient donc être faux partout, et **tous les lieux restent `legacy`** (décision 1). Rien ne prouve qu'un lieu n'a pas hérité d'un drapeau à vrai : la copie de prod le compte **avant** la bascule (§8). Si le comptage n'est pas 0, `0227` passerait ces lieux en `v2`, contrairement à la décision 1 : le signaler au mainteneur avant la bascule |
| **dev** (vérifié le 2026-10-06) | `lespass`, `le-coeur-en-or`, `la-maison-des-communs`, `le-reseau-des-lieux-en-reseau` ont caisse + monnaie locale + kiosk → `v2`. `festival` et `meta` n'en ont aucun → `legacy`. `festival` joue le rôle de CLAF dans les tests (`14-spec-tests-federation-inter-lieux.md`) |
| **nouveau lieu** | pas de `Configuration` au moment de la migration → reste `v2` (défaut) |

**Les schémas `test_*` de la base de dev (vérifié) :** `FastTenantTestCase` **réutilise** la
ligne `Client` d'un schéma `test_*` qui existe déjà (`use_existing_tenant`). Les 45 schémas
`test_*` n'ont aucun drapeau V2 en base (les tests posent `module_caisse = True` dans leur
`setUp`, puis rollback) : `0227` les laisse `legacy`, et les tests caisse V2, kiosk et tireuse
tomberaient sur le verrou.

C'est la règle déjà écrite dans le skill `tibillet-test` : **toute nouvelle migration périme
les schémas `test_*`**. Après `migrate_schemas`, la purge de ces schémas (procédure du skill,
qui supprime aussi leurs lignes `Customers_client`) est **obligatoire** ; ils sont recréés au
lancement suivant, donc en `v2`. La purge est destructive (schémas de test seulement) : elle
est lancée par le mainteneur ou avec son accord, et écrite **en tête** du CHANGELOG. Ne pas
ajouter d'exception sur le préfixe `test_` dans la migration.

### 4.3 Jeu de démo

`Administration/management/commands/demo_data_v2.py` crée ses lieux **après** les migrations :
ils sont tous `v2` par défaut. Il doit **poser explicitement `festival` en `legacy`**, pour
garder le profil CLAF des tests sur une base de dev reconstruite. Le reste ne change pas.

## 5. Ce que le verrou ferme pour un lieu `legacy`

Une seule lecture partout : `connection.tenant.moteur_monnaie == Client.MOTEUR_LEGACY`, par
la fonction `Customers.models.lieu_en_moteur_legacy()`. Le schéma public n'est pas un lieu :
il est **toujours fermé**, quelle que soit la valeur de sa ligne `Client` (session 15-bis, M1).

**Piège à vérifier (`tests/PIEGES.md`, FakeTenant)** : sous `schema_context()`,
`connection.tenant` est un `FakeTenant` sans ce champ. Lire avec
`getattr(connection.tenant, "moteur_monnaie", None)` et décider **explicitement** du cas
`None`. Recommandation : `None` = fermé (on ne sait pas, on ne bascule pas). Vérifié : en HTTP
(`TenantMainMiddleware`), en WebSocket (`wsocket/middlewares.py:59`) et dans les tâches
Celery du projet (`tenant_context`), `connection.tenant` est un vrai `Client`. Les trois
permissions du §5.4 lisent déjà `connection.tenant.pk` : pas de cas `FakeTenant` légitime.

### 5.1 Activation des modules — `module_toggle`

**Fichier :** `Administration/admin_tenant.py:608`.

- Modules fermés en legacy : `module_monnaie_locale`, `module_caisse`, `module_kiosk`,
  `module_tireuse`.
- `module_inventaire` (stock des articles de caisse) n'est pas monétaire : il reste ouvert.
  Sans caisse, il n'a pas d'usage.
- Refus **côté serveur**, avant tout `setattr` : message d'erreur FALC (« Votre lieu utilise
  l'ancien moteur de monnaie (Fedow). Ce module n'est pas disponible. »), aucune écriture,
  même réponse `HX-Refresh` que les refus existants de la méthode.
- **Désactiver** un de ces modules reste permis (un lieu legacy qui aurait un drapeau à vrai
  doit pouvoir l'éteindre).

### 5.2 Tableau de bord — les cartes de module

**Fichiers :** `Administration/admin/dashboard.py` (cartes de module, `montre_interrupteur`,
~l.2455-2620) et `Administration/templates/admin/partials/dashboard_module_card.html`.

- Pour un lieu legacy, les quatre cartes de modules V2 portent un drapeau dédié
  **`carte.moteur_legacy = True`**, `montre_interrupteur = False`, et le gabarit a une branche
  pour ce drapeau qui affiche la phrase du §5.1. **Ne pas** se contenter de
  `montre_interrupteur = False` : la branche `else` actuelle du gabarit (~l.95-110) affiche
  « V1 active » et une pastille en ligne / hors ligne.
- La carte caisse d'un lieu LaBoutik V1 garde son état `v1_active` et son lien « Open
  LaBoutik V1 » : inchangés.

### 5.3 Admin `fedow_core`

**Fichier :** `fedow_core/admin.py`.

- `AssetAdmin`, `TokenAdmin`, `TransactionAdmin`, `FederationAdmin` : `has_view_permission`,
  `has_add_permission`, `has_change_permission` renvoient `False` pour un lieu legacy, **en
  plus** de la règle actuelle. L'URL directe répond 403.
- **Les routes personnalisées ne lisent pas ces méthodes** : elles passent par
  `admin_site.admin_view`, qui ne vérifie que `is_active` / `is_staff`. Chacune refuse donc
  **elle-même** un lieu legacy (même message que §5.1) :
  - `AssetAdmin.accept_asset_invitation` (~l.418) ;
  - `FederationAdmin.accept_invitation` et `FederationAdmin.remove_member` (`get_urls`
    l.854-875, vues ~l.880 et ~930).
- **Invitations V2 : un lieu legacy n'est jamais invitable.**
  - **La validation** se fait par le queryset du champ : `AssetAdmin.formfield_for_manytomany`
    pour `pending_invitations` → `Client.objects.filter(moteur_monnaie='v2')`, en gardant les
    exclusions habituelles (`WAITING_CONFIG`, `ROOT`, `META`). Un pk forcé vers un lieu
    legacy doit être **refusé** par le formulaire. Commentaire obligatoire, au présent :
    l'autocomplétion ne pilote que l'affichage, c'est ce queryset qui valide.
  - **L'affichage** : `TenantAdmin.get_search_results` (`admin_tenant.py:5533`) exclut les
    lieux legacy quand la requête d'autocomplétion vient de ce champ. Lire les paramètres
    GET de l'autocomplétion Django (`app_label=fedow_core`, `model_name=asset`,
    `field_name=pending_invitations`), pas le `Referer`.
  - `save_related` (protection existante de `pending_invitations`) : défense en profondeur,
    retire tout lieu legacy qui y serait arrivé.
- **Second chemin d'invitation : les fédérations V2.** `FederationAdmin` invite des lieux par
  `pending_tenants` (`autocomplete_fields`, `fedow_core/admin.py:715`). Même traitement :
  `FederationAdmin.formfield_for_manytomany` (`pending_tenants` →
  `Client.objects.filter(moteur_monnaie='v2')` + exclusions habituelles), et
  `TenantAdmin.get_search_results` filtre aussi `app_label=fedow_core`,
  `model_name=federation`, `field_name=pending_tenants`.

### 5.4 Défense en profondeur — les points d'entrée V2

Même si un drapeau était resté à vrai en base :

| Fichier | Classe | Ajout |
|---|---|---|
| `BaseBillet/permissions.py` (~l.112) | `HasLaBoutikTerminalAccess` | refus si legacy, avant la garde `module_caisse` |
| `kiosk/views.py` (~l.70) | `IsKioskTerminal` | refus si legacy |
| `controlvanne/permissions.py` (~l.42) | `HasTireuseAccess` | refus si legacy |
| `BaseBillet/views.py` | `get_distant_fedow_tokens` (sert `MyAccount.tokens_table` et l'index V2) et `MyAccount.admin_my_cards` | n'appellent pas `_agreger_tokens_locaux` si legacy |
| `ApiBillet/views.py` | `Onboard_laboutik` | refuse un lieu **v2** (409, `code = "lieu_en_moteur_v2"`), avant le verrou des modules : un lieu v2 n'a jamais de caisse LaBoutik V1 (décision I1, session 15-bis) |

On garde `_agreger_tokens_locaux` tel quel : `tests/pytest/test_balance_soldes_et_recharge.py`
l'appelle hors `tenant_context` (l.203 à 355), où `connection.tenant` peut être un
`FakeTenant` ; y lire le moteur rendrait ces tests faux ou instables. Les deux appelants HTTP,
eux, ont le vrai `Client`.

Pour chacun : commentaire qui énonce la contrainte au présent (« un lieu legacy n'utilise que
l'ancien Fedow : … »).

### 5.5 Menu latéral

> **Réécrit le 2026-10-06 (décision Q1 du mainteneur, suivi `CHANTIER-15-10-14-SUIVI.md` §5)** :
> plus d'entrée directe en tête du menu ; une seule porte, la section « Monnaies ».

**Fichier :** `Administration/admin/dashboard.py`.

- Les sections des modules V2 (`module_caisse`, « Terminaux matériels », « Inventaire » —
  conditionnée sur `module_caisse` seul —, tireuse, kiosk) exigent **en plus** un lieu `v2`.
- **La section « Monnaies »** (page de module, slug `monnaies`, onglets Gérer / Configurer /
  Analyser) suit le moteur du lieu :
  - lieu `v2` : comme aujourd'hui (« Monnaies et tokens » `fedow_core`, fédérations V2,
    transactions), **plus** l'élément « Assets legacy » (`staff_admin:fedow_public_assetfedowpublic_changelist`)
    dans « Gérer », **seulement si** le lieu a des assets legacy : `AssetFedowPublic` non archivé
    dont il est l'origine, ou où il est dans `federated_with` ou `pending_invitations` (catégories
    FED, BDG, SUB exclues : le FED est accepté partout). C'est ce qui permet à un lieu V2 invité par
    CLAF de voir l'invitation et de l'accepter ;
  - lieu `legacy` : la section s'affiche si `configuration.module_federation` est allumé **ou** si
    le lieu a des assets legacy (même condition) ; elle ne contient que « Assets legacy » (onglet
    « Gérer ») ; un onglet sans page n'apparaît pas.
- **Libellés** : les noms actuels, avec « legacy » ajouté aux éléments legacy (« Assets legacy »).
- L'entrée « Assets » du module « Fédération et agenda participatif » est **retirée** (elle vit
  dans « Monnaies ») : une page n'appartient qu'à une section (`test_aucune_page_n_appartient_a_deux_modules`).
- La carte du module « Monnaie locale » du tableau de bord reste fermée pour un lieu `legacy`
  (§5.2) : la carte parle du module V2 qu'on peut allumer, le menu des monnaies que le lieu gère.
- `_construire_sections_modules` est appelé 4 fois par page admin (menu latéral, deux fois
  les onglets, fil d'Ariane). La requête « le lieu a des assets legacy » est mémorisée sur la
  requête HTTP (`_lieu_a_des_assets_legacy`, comme `_tb_badge_propositions`) : elle ne tourne
  qu'une fois par page (session 15-bis).
- **Voulu** (décision M7 du mainteneur) : un lieu v2 sans asset legacy n'a pas d'entrée vers
  les assets legacy ; il crée ses monnaies dans `fedow_core`.

### 5.6 Ce qui reste ouvert pour un lieu legacy

Tout l'ancien Fedow, à l'identique de `main` : admin `AssetFedowPublic` (création,
invitation, acceptation, fiche, ventilation, remise en banque), `/fedow/asset/…`, recharge
FED, remboursement, paiement QR/NFC de « Mon compte », récompenses d'adhésion, LaBoutik V1.

### 5.7 Laissé ouvert volontairement (aucun mouvement d'argent)

- Les admins par URL directe de `laboutik.*`, `kiosk.borne`, `controlvanne.*`,
  `inventaire.*` ; l'appairage `discovery/views.py:29` (`AllowAny`) ; l'écran
  `controlvanne/kiosk/` (`controlvanne/viewsets.py:1294`) et les pages de calibration ; le
  pont `laboutik/views.py:15464` (pose seulement le cookie). L'argent, lui, passe toujours
  par `HasLaBoutikTerminalAccess`, `IsKioskTerminal` ou `HasTireuseAccess`, fermés au §5.4.
- Deux flux legacy de « Mon compte » écrivent déjà dans `fedow_core` et restent tels quels :
  `CarteService.lier_a_user` (`BaseBillet/views.py:750`) et `CarteService.declarer_perdue`
  (`:1521`). Sur une carte de prod (sans `wallet_ephemere`), ils posent seulement
  `CarteCashless.user`, champ qui existe déjà sur `main`.

## 6. Ce qui reste ouvert pour un lieu `v2`

Rien ne change par rapport à aujourd'hui. Un lieu `v2` peut aussi être invité sur un asset
legacy (CLAF) et l'accepter dans l'admin legacy : le lien du §5.5 s'affiche dès qu'il a une
invitation en attente.

## 7. Tests

Lire `tests/PIEGES.md` avant d'écrire. Chaque test doit être vu **échouer** sur une
mutation volontaire.

**Fichier :** `tests/pytest/test_verrou_moteur_legacy.py`.

Pour passer un lieu en legacy le temps d'un test : `Client.objects.filter(pk=…).update(…)`
sous `django_db` (rollback), et relire `connection.tenant` ou passer par le client HTTP (le
middleware relit le `Client`). Ne pas toucher aux singletons django-solo en base (cache
memcached partagé, PIEGES 9.86).

| Test | Attendu |
|---|---|
| un `Client` créé après la migration | `moteur_monnaie == 'v2'` |
| fonction `RunPython` de `Customers 0006`, appelée directement | `WAITING_CONFIG` → `v2`, les autres inchangés |
| fonction `RunPython` de `BaseBillet 0227`, lieu avec un drapeau V2 à vrai | `Client` → `v2` |
| idem, lieu sans drapeau V2 | `Client` reste `legacy` |
| idem, schéma sans `Configuration` | rien ne change, aucune erreur |
| `module_toggle` sur chacun des 4 modules, lieu legacy | drapeau inchangé, message d'erreur |
| `module_toggle` désactivation, lieu legacy avec drapeau à vrai | désactivé |
| `module_toggle`, lieu v2 | comportement actuel (non-régression) |
| `module_toggle` POST direct `module_caisse`, lieu legacy avec `server_cashless` | refusé |
| `/admin/fedow_core/asset/`, `/add/`, tokens, transactions, fédérations, lieu legacy | 403 |
| idem, lieu v2 | 200 |
| `accept_asset_invitation`, lieu legacy | refusé, rien ne bouge |
| `FederationAdmin.accept_invitation` et `remove_member`, lieu legacy | refusés, rien ne bouge |
| formulaire de fédération V2 avec un pk de lieu legacy forcé dans `pending_tenants` | formulaire invalide |
| fonction `RunPython` de `BaseBillet 0227` : le lieu basculé est journalisé | ligne imprimée |
| `tokens_table` et `admin_my_cards`, lieu legacy avec `module_monnaie_locale` à vrai | aucun token local ajouté |
| formulaire d'asset V2 avec un pk de lieu legacy forcé dans `pending_invitations` | formulaire invalide, aucune invitation |
| autocomplétion `pending_invitations` | aucun lieu legacy proposé |
| `HasLaBoutikTerminalAccess`, `IsKioskTerminal`, `HasTireuseAccess`, lieu legacy avec drapeau à vrai | refus |
| menu latéral, lieu legacy + `module_federation` | section « Monnaies » avec seulement « Assets legacy » ; sections V2 absentes |
| menu latéral, lieu v2 sans asset legacy | pas d'« Assets legacy » dans la section « Monnaies » |
| menu latéral, lieu v2 avec une invitation legacy en attente | « Assets legacy » dans l'onglet « Gérer » de la section « Monnaies » |
| carte de module V2 au tableau de bord, lieu legacy | pas d'interrupteur, phrase affichée, pas d'encart BETA |
| total d'un domaine du tableau de bord, lieu legacy | 0 / N (cartes fermées comptées) ; la pastille « Découvrir » les écarte |
| `Onboard_laboutik`, lieu v2 | refus 409, rien écrit ; lieu legacy : comme avant |
| `lieu_en_moteur_legacy()` sur le schéma public | fermé, quelle que soit la valeur de sa ligne `Client` |

**Tests existants à surveiller :** les suites caisse V2, kiosk, tireuse, `fedow_core`
tournent sur des lieux de dev (`lespass`…), qui passent `v2` par la migration 0227 (§4.2).
Voir aussi la vérification des schémas `test_*` (§4.2). Si un test crée son propre lieu
(`FastTenantTestCase`, `test_*`), il est `v2` par défaut : rien à faire. `tests/pytest/conftest.py`
a une vérification de départ **automatique** (fixture autouse de portée session
`_moteurs_verifies_au_depart_de_la_suite`, une requête) qui **échoue** avec la consigne si
`lespass` n'est pas `v2` **ou si une ligne `Client` `test_*` est `legacy`** (consigne : base
neuve par `down -v` + flush, ou mise à jour SQL des `test_*`). La vérification complète
(`festival` legacy, `le-coeur-en-or` v2) reste à la demande (`moteurs_de_depart_verifies`).
Jamais de `skip`.

**E2E :** `14-spec-tests-federation-inter-lieux.md` ajoute ses prérequis : `lespass` et
`le-coeur-en-or` en `v2`, `festival` en `legacy`.

## 8. Chantier R (copie de prod) — cases à ajouter

> **Fait en session 15-4 (2026-10-06)** : les cases sont dans
> `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-copie-prod.md` §3.5 (« Vérifications du
> moteur de monnaie et du réseau CLAF ») ; la première est la sous-commande `compter_avant`
> de `db-prod/copie_prod.sh` ; la fiche R §7.2 (étape 3, vérification c) la reprend.

Ordre sur la copie : `charger` → **`compter_avant`** → `neutraliser` → `migrer` → `compter`.
Comptages agrégés seulement, en lecture seule :

- [ ] **Avant `neutraliser`** (la neutralisation vide `server_cashless`) :
      `bash db-prod/copie_prod.sh compter_avant`. Sous-commande en **lecture seule**
      (transaction `READ ONLY`, psql seul, aucun `manage.py`), sans aucune donnée
      personnelle. Gardes : la pile est la bonne, un dump est chargé, la neutralisation n'est
      **pas** faite (sinon : « trop tard, `server_cashless` est vidé »). Elle affiche, par
      catégorie de lieu puis au total : nombre de lieux, lieux dont la `Configuration` a
      `module_caisse`, `module_monnaie_locale`, `module_kiosk`, `module_tireuse` à vrai, et
      au moins un des quatre ; lieux avec `server_cashless` renseigné (compté, jamais
      affiché) ; lieux `module_federation`. `module_kiosk` n'existe pas sur `main` : une
      colonne absente compte « faux » (la sous-commande liste les colonnes absentes).
      **Attendu : 0 lieu de production (hors pool `W`) avec un des quatre drapeaux à vrai.**
      Sinon : **STOP**, le signaler au mainteneur ; décision avant la bascule, car `0227`
      passerait ces lieux en `v2` (§4.2).
- [ ] **Après `migrer`** : `SELECT moteur_monnaie, categorie, count(*) FROM
      public."Customers_client" GROUP BY 1, 2`. Attendu : tous `legacy`, sauf
      `WAITING_CONFIG` en `v2`, et les lieux listés par `0227` dans le journal de migration
      (attendu : aucun, cf. case précédente).
- [ ] **Avant / après `migrer`** : empreinte du miroir `public.fedow_public_assetfedowpublic`
      et de ses tables M2M `federated_with` et `pending_invitations` (`md5(string_agg(… ORDER
      BY …))`). Empreintes identiques.
- [ ] **CLAF** : pour les assets dont le nom commence par « CLAF », même nombre de lieux dans
      `federated_with` avant et après, `archive` faux.
- [ ] **Après `migrer`** : tables `fedow_core_*` (asset, token, transaction, federation) à 0
      ligne.
- [ ] **Hors copie, la nuit de la bascule** : capture de la fiche de l'asset CLAF
      (ventilation par lieu) et de `/fedow/asset/<uuid>/retrieve_bank_deposits/` avant la
      bascule, même page après, mêmes chiffres. Aucun POST de remise en banque (irréversible).

## 9. Fichiers touchés

Liste réelle, complétée en session 15-4 (2026-10-06).

| Session | Fichier | Changement |
|---|---|---|
| 15-1 | `Customers/models.py` | `Client.moteur_monnaie` (§3), fonction `lieu_en_moteur_legacy()` (`None` = fermé, §5) |
| 15-1 | `Customers/migrations/0006_moteur_de_monnaie.py` | nouveau (§4.1) |
| 15-1 | `BaseBillet/migrations/0227_moteur_v2_si_un_module_v2_est_actif.py` | nouveau (§4.2) |
| 15-1 | `Administration/management/commands/demo_data_v2.py` | `festival` en legacy, par le drapeau `caisse_v1_legacy` (§4.3) |
| 15-1 | `tests/pytest/test_fedow_core.py` | le second lieu V2 est `le-coeur-en-or` (`festival` est legacy) |
| 15-2 | `Administration/admin_tenant.py` | `module_toggle` (§5.1), `TenantAdmin.get_search_results` (§5.3) |
| 15-2 | `fedow_core/admin.py` | permissions, routes personnalisées, querysets des invitations, `save_related` (§5.3) |
| 15-2 | `BaseBillet/permissions.py`, `kiosk/views.py`, `controlvanne/permissions.py` | défense en profondeur (§5.4) |
| 15-2 | `BaseBillet/views.py` | `get_distant_fedow_tokens` et `admin_my_cards` sans tokens locaux en legacy (§5.4) |
| 15-2 | `tests/pytest/test_pos_vider_carte.py` | fragilité hors verrou (fixture `asset_tlf_vc` dans le schéma public) |
| 15-3 | `Administration/admin/dashboard.py` | cartes de module (§5.2), menu latéral et section « Monnaies » (§5.5) |
| 15-3 | `Administration/templates/admin/partials/dashboard_module_card.html` | branche `moteur_legacy`, phrase du verrou (§5.2) |
| 15-1 à 15-3 | `tests/pytest/test_verrou_moteur_legacy.py` | nouveau, 27 tests (§7) |
| 15-1, 15-4 | `tests/pytest/conftest.py` | fixture `moteurs_de_depart_verifies` (§7) ; la fonction est déplacée en 15-4 |
| — | `tests/pytest/test_admin_fil_ariane_et_rail.py` | **non modifié** : l'invariant « une page, une section » tient sans retouche (« Assets » sort du module Fédération, §5.5) |
| 15-4 | `tests/outils_moteur_de_monnaie.py` | nouveau : `verifier_les_moteurs_de_depart()`, importable par pytest et par les E2E (prérequis de la spec 14) |
| 15-4 | `tests/e2e/conftest.py` | fixture E2E `moteurs_de_depart_verifies` (à demander, pas appliquée à toute la suite) |
| 15-4 | `db-prod/copie_prod.sh` | **hors git** (`db-prod/` est ignoré) : sous-commande `compter_avant` (§8) |
| 15-4 | `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-copie-prod.md` | ordre `charger` → `compter_avant` → `neutraliser` → `migrer` → `compter` ; cases du §8 (§3.5) |
| 15-4 | `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md` | §7.2 : liste réelle des migrations de la nuit, vérification `compter_avant`, lieux `legacy` après `0006` ; §11 : migrations, moteur et reprise |
| 15-4 | `TECH_DOC/SESSIONS/FEDOW_IMPORT/INDEX.md` | specs 10, 14, 15 et suivi du chantier 15 · 10 · 14 |
| 15-4 | `TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md` | §8 et §9 (ce document) |
| — | `TECH_DOC/SESSIONS/FEDOW_IMPORT/14-spec-tests-federation-inter-lieux.md` | prérequis de moteur déjà écrits (§2) ; rien à changer |
| 15-bis | `ApiBillet/views.py` | `Onboard_laboutik` refuse un lieu v2 (I1) |
| 15-bis | `Customers/models.py` | `lieu_en_moteur_legacy()` : public toujours fermé (M1) ; `MODULES_V2_FERMES_AUX_LIEUX_LEGACY` et `MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY` déménagés ici (M8) |
| 15-bis | `Administration/admin/dashboard.py` | pas d'encart BETA sur une carte fermée (M2) ; total du domaine 0 / N (M3) ; assets legacy lus une fois par requête (M4) |
| 15-bis | `Administration/admin_tenant.py`, `fedow_core/admin.py`, `BaseBillet/permissions.py` | imports des constantes et de `lieu_en_moteur_legacy` en tête de fichier (M8) |
| 15-bis | `tests/outils_moteur_de_monnaie.py`, `tests/pytest/conftest.py`, `tests/e2e/conftest.py` | vérification de départ automatique (I2) ; imports en tête (M8) |
| 15-bis | `tests/pytest/test_onboard_laboutik_verrou_v1_v2.py` | réécrit sur le lieu dédié `test_verrou_moteur_legacy` (plus `lespass`) |
| 15-bis | `tests/pytest/test_card_refund_service.py`, `test_remboursement_especes_trace_comptable.py`, `test_verify_transactions.py`, `tests/PIEGES.md` | asset TLF des fixtures de portée module créé sous `schema_context(public)` ; piège 15.1 (M6) |
| 15-bis | `tests/pytest/test_verrou_moteur_legacy.py` | tests 23 à 29 |
| 15-1 à 15-bis | `CHANGELOG/2026-10-06-verrou-moteur-legacy.md` | nouveau ; une section par session, résumé en tête |

**Migration :** oui — `Customers 0006` (schéma public) et `BaseBillet 0227` (chaque lieu).
`migrate_schemas --executor=multiprocessing`. Aucune étape manuelle.

**Traductions :** nouvelles chaînes en français (§3, §5.1, §5.5) → signaler au mainteneur que
le workflow i18n est à lancer. Ne jamais lancer `makemessages`.

## 10. Hors périmètre

- Tout outil de bascule d'un lieu existant vers V2 (plus tard, sur décision du mainteneur).
- Toute migration de données legacy → `fedow_core` (S4, non acté).
- Les impacts acceptés du §2.5.
