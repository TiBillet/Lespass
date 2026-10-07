# 14 — Spec : tests de la fédération d'assets entre deux lieux, avec le vrai Fedow

**Date :** 2026-10-06
**Statut :** spec validée dans son principe par le mainteneur — rien n'est codé.

---

## 1. Pourquoi

Le parcours « un lieu émet une monnaie, la fédère avec un autre lieu, un adhérent la reçoit
chez le premier et la dépense chez le second » fonctionne en production (branche `main`,
réseau CLAF : un asset TLF fédéré entre ~36 lieux). **Aucun test ne fait intervenir deux
lieux**, ni sur `main` ni sur cette branche :

- tous les E2E contre le vrai Fedow tournent sur le seul lieu `lespass` ;
- l'invitation et l'acceptation de fédération (`AssetAdmin.accept_invitation` →
  `FedowAPI.federation.create_fed`) n'ont **aucun** test, ni réel ni simulé ;
- la fiche d'un asset (lieux fédérés, ventilation par lieu, bouton de remise en banque,
  `Administration/admin_tenant.py` `AssetAdmin.changeform_view`) n'a **aucun** test ;
- la dépense chez un lieu B d'une monnaie émise par un lieu A n'est testée qu'en simulé
  (`tests/pytest/test_fedow_solde_depensable.py`).

Ces tests prouvent que les lieux existants, qui restent sur l'ancien Fedow (décision S6),
ne cassent pas avec cette branche.

Les outils multi-lieux existent déjà dans `tests/e2e/conftest.py` mais aucun test ne les
utilise : `django_shell(code, schema=...)` et `login_as_admin_on_subdomain(page, subdomain)`.

## 2. Les lieux de dev utilisés

Vérifié le 2026-10-06 sur la base de dev :

| Lieu | `FedowConfig.get_solo().can_fedow()` | `module_monnaie_locale` | Rôle dans les tests |
|---|---|---|---|
| `lespass` | oui | oui | émetteur de la monnaie, lieu de l'adhésion |
| `festival` | oui | **non** | lieu fédéré, **profil de CLAF** : ancien Fedow seul. Skin `faire_festival` → pages compte du skin classic |
| `le-coeur-en-or` | oui | oui | second lieu pour le test V2 (`fedow_core`) |

L'ancien test Playwright utilisait `chantefrein`, qui n'existe plus en dev.

**Moteur de monnaie** (`Client.moteur_monnaie`, spec `15-spec-verrou-moteur-legacy.md`) :
`lespass` et `le-coeur-en-or` en `v2`, `festival` en `legacy`. Si la spec 15 est livrée
avant ces tests, les vérifier au départ (échec explicite sinon).

## 3. Les trois tests

### Test A — fédération V2 (`fedow_core`) : portage de l'ancien test Playwright

**Source :** `tests/playwright/tests/admin/31-admin-asset-federation.spec.ts`, supprimé par
le commit `35dc0cc1` (2026-03-21), jamais réécrit en Python. Lisible avec
`git show 35dc0cc1^:tests/playwright/tests/admin/31-admin-asset-federation.spec.ts`.

**Attention :** ce test vise l'admin **V2** `/admin/fedow_core/asset/`, pas l'admin legacy.
Il ne prouve rien pour CLAF. On le porte parce qu'il couvre la fédération `fedow_core`, elle
aussi sans test E2E.

**Fichier :** `tests/e2e/test_federation_asset_fedow_core.py`. Pas d'appel au Fedow distant.

**Lieux :** `lespass` → `le-coeur-en-or` (les deux ont `module_monnaie_locale`, prérequis de
l'ancien test).

Étapes, reprises de l'ancien test :
1. Admin sur `lespass`, `/admin/fedow_core/asset/add/` : crée un asset TLF au nom unique par
   lancement (`E2E Fed V2 <suffixe>`).
2. Fiche de l'asset : invite `le-coeur-en-or` dans `pending_invitations` (champ en
   autocomplétion Unfold — voir `tests/PIEGES.md`, Tom Select).
3. Liste filtrée par nom (`?q=`) : la colonne « Lieux fédérés » montre `lespass`, **pas**
   encore `le-coeur-en-or`.
4. Admin sur `le-coeur-en-or` (`login_as_admin_on_subdomain`) : l'invitation est visible, il
   l'accepte (`accept_asset_invitation`).
5. Les deux lieux voient l'asset ; la colonne « Lieux fédérés » montre les deux.

### Test B — fédération legacy (`AssetFedowPublic`) avec le vrai Fedow

C'est l'équivalent legacy du test A. **Il n'a jamais existé**, ni sur `main` ni ici.

**Fichier :** `tests/e2e/test_federation_asset_legacy_inter_lieux.py` — même fichier que le
test C, voir 3.3.

Étapes :
1. Admin sur `lespass`, `/admin/fedow_public/assetfedowpublic/add/` : crée un asset TLF au nom
   unique (`E2E Fed legacy <suffixe>`). Vérifie qu'il existe **sur le Fedow**
   (`save_model` → `get_or_create_token_asset`).
2. Fiche de l'asset : invite `festival` (`pending_invitations`, réservé au lieu d'origine).
3. Admin sur `festival` : la liste `/admin/fedow_public/assetfedowpublic/` montre
   l'invitation ; il clique sur « Accepter » (`accept_invitation`, qui appelle `create_fed`
   **dans le contexte du lieu d'origine**).
4. Vérifications :
   - en base (`django_shell`, schéma public) : `festival` est passé de `pending_invitations`
     à `federated_with` ;
   - **sur le Fedow** : `get_accepted_assets()` lancé dans le contexte de `festival` renvoie
     l'asset ;
   - fiche de l'asset chez `lespass` : `festival` apparaît parmi les lieux fédérés.

### Test C — le parcours complet entre les deux lieux

Suite directe du test B, **même lancement, même asset**. Demande du mainteneur : la dépense
se fait sur `festival`, par l'adhérent qui a pris son adhésion sur `lespass`.

1. **Le tarif de test** (`django_shell` sur `lespass`) : un produit adhésion et un tarif
   dédiés au lancement, avec `fedow_reward_enabled`, `fedow_reward_asset` = l'asset du
   test B, `fedow_reward_amount`.
   - On ne réutilise **pas** « Caisse de sécurité sociale alimentaire » : sa monnaie
     (MonaLocalim) n'est pas fédérée avec `festival`, et le test B doit rester maître de la
     fédération qu'il vérifie.
2. **L'adhésion chez `lespass`** : adhérent neuf à l'email validé + portefeuille, adhésion
   en attente, cotisation enregistrée en espèces par l'admin
   (`/memberships/<pk>/ajouter_paiement/`), comme `test_adhesion_recompense_puis_qrcode.py`.
   Attendre le versement : solde relu **sur le Fedow** (`use_cache=False`) = récompense.
3. **Le QR code créé sur `festival`, dans le navigateur** : admin de `festival` →
   `/my_account/` → tuile « My wallet » → `/my_account/balance/` → « Initiate a payment »
   → montant dans `#amount` → « Initier un paiement ». C'est le parcours du skin classic,
   celui des lieux legacy. On lit le lien de paiement dans `data-link` de
   `#copy-pay-link-btn`.
4. **Le paiement par l'adhérent sur `festival`** : l'adhérent se connecte sur `festival`,
   ouvre le lien de paiement (remplace la caméra : c'est l'URL du QR code), voit l'écran de
   validation, clique « Confirm Payment », voit « Payment Confirmed ».
   **Piège du cache** : `valid_payment` lit le solde **avec** cache
   (`get_total_fiducial_and_all_federated_token(user)`, cache de 10 s,
   `fedow_connect/fedow_api.py:420-427`). Le lien de paiement ne doit être ouvert **qu'après**
   la fin de l'étape 2 (versement constaté sur le Fedow), sinon un solde lu trop tôt fait
   tomber le paiement en « fonds insuffisants ».
5. **Le Fedow a débité** le montant exact de la monnaie de `lespass`, dans le portefeuille de
   l'adhérent.
6. **La vente est chez `festival`** (`django_shell(schema="festival")`) : la ligne de la
   demande est validée, au bon montant, avec le moyen de paiement de la monnaie locale.
   Rien côté `lespass`.
7. **La fiche de l'asset chez `lespass`** (admin, navigateur) : `festival` est fédéré, et le
   tableau de ventilation (en-têtes « Lieu / Total / Action »,
   `Administration/templates/admin/asset/asset_change_form_before.html:49-51` ; il n'a pas de
   titre « Ventilation par lieu ») montre une ligne `festival` égale au montant dépensé.
   Cibler ces libellés, ou ajouter des `data-testid` au gabarit.
8. **La remise en banque** : l'admin de `lespass` clique « Valider le retour en banque » sur
   la ligne `festival` (`hx-post …/bank_deposit/<asset>/<wallet>/`). La ventilation de
   `festival` revient à 0 sur le Fedow, et `/fedow/asset/<uuid>/retrieve_bank_deposits/`
   affiche la remise de `festival`.

**Point à confirmer pendant l'écriture du test (étape 8) :** sur `main`, le bouton de remise
s'affiche sur chaque ligne de la ventilation, et Lespass ne vérifie que « admin du lieu ».
On teste le cas prévu : le lieu d'origine remet en banque la part d'un lieu fédéré. Si le
Fedow refuse, c'est une information à remonter au mainteneur, pas un test à adapter.

### 3.3 Organisation des fichiers

- Tests B et C dans **un seul parcours** (`test_parcours_monnaie_federee_entre_deux_lieux`),
  dans le style de `test_adhesion_recompense_puis_qrcode.py` : étapes numérotées, messages
  d'échec qui disent quoi regarder. Le test C dépend de l'asset du test B ; les séparer
  obligerait à faire la fédération dans une fixture, où les vérifications n'ont pas leur
  place.
- Test A dans son propre fichier : autre moteur, autres lieux, pas de Fedow distant.

## 4. Ce qu'il faut ajouter aux outils de test

- **Connexion d'un adhérent sur un autre lieu.** `login_as` ne connecte que sur `lespass`, et
  `login_as_admin_on_subdomain` que l'admin. Ajouter dans `tests/e2e/conftest.py` une fixture
  `login_as_on_subdomain(page, email, subdomain)`, sur le modèle de
  `login_as_admin_on_subdomain` (header `Host` du lieu, cookie posé sur
  `<subdomain>.<DOMAIN>`).
- **Deux contextes de navigateur** (`browser.new_context()`) : l'admin de `festival` garde
  la page du générateur ouverte pendant que l'adhérent paie.
- Les lectures en base sur `festival` passent par `django_shell(code, schema="festival")`.

## 5. Contraintes

- **Vrai Fedow, pas de rollback.** Chaque lancement crée un asset et émet une récompense sur
  le Fedow de dev. C'est le même compromis que les E2E existants : à lancer sur un Fedow de
  développement uniquement. Le dire dans l'en-tête des fichiers.
- **Prérequis vérifiés au départ, échec explicite sinon** (jamais de `pytest.skip`) :
  `FedowConfig.get_solo().can_fedow()` vrai sur `lespass` et `festival`, Celery qui tourne, Fedow joignable,
  `festival` sans `module_monnaie_locale` (sinon il ne joue plus le rôle de CLAF).
- **Noms uniques par lancement** (suffixe aléatoire) et listes filtrées par `?q=` : la base
  de dev garde les assets des lancements précédents.
- **Lire `tests/PIEGES.md` avant d'écrire**, notamment : Tom Select d'Unfold, `django_shell`
  qui pose le vrai lieu (pas `schema_context`), cookies par sous-domaine.
- Chaque test doit être vu **échouer** sur une mutation volontaire avant d'être livré
  (exemples : ne pas accepter l'invitation → l'étape 4 du test B tombe ; payer sur un lieu
  non fédéré → l'étape 4 du test C tombe en « fonds insuffisants »).

## 6. Fichiers

| Fichier | Changement |
|---|---|
| `tests/e2e/test_federation_asset_fedow_core.py` | nouveau — test A |
| `tests/e2e/test_federation_asset_legacy_inter_lieux.py` | nouveau — tests B et C |
| `tests/e2e/conftest.py` | fixture `login_as_on_subdomain` |
| `tests/PIEGES.md` | pièges rencontrés pendant l'écriture |
| `CHANGELOG/2026-10-xx-tests-federation-inter-lieux.md` | nouveau |

## 7. Hors périmètre

- La dépense par NFC (LaBoutik V1 ou caisse V2) d'une monnaie fédérée chez un autre lieu.
  Possible ensuite sur le même asset ; la répartition est déjà couverte par
  `test_c2_legacy_repartition.py`.
- Le verrou qui empêche un lieu legacy de basculer en V2 : spec à part (point 4 de la
  discussion du 2026-10-06).
