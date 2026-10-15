# Chantier 03 — Le FED invisible en caisse V2 (carte liée par QR, carte anonyme)

> Ouvert le 2026-10-14, à la suite d'un bug de production.
> Statut : **correction codée le 2026-10-14 (feu vert du mainteneur), non commitée.**
> Voir §5. Les tests rouges du §4 sont verts ; E2E à relancer avec le Fedow de dev.
> Annexe : [`CHANTIER-03-annexe-audit-tests.md`](CHANTIER-03-annexe-audit-tests.md)
> (audit des tests qui verrouillent un bug, agent Opus, 2026-10-14).

## 1. Le bug

Un lieu existait avant la migration V2. Il n'avait pas de LaBoutik V1, et il a ouvert le
module de caisse V2. Ses cartes sont chargées **chez l'ancien Fedow seulement**.

1. Une personne scanne le QR de sa carte et donne son email (`/qr/<uuid>/`, puis
   `POST /qr/link/`).
2. Elle recharge du FED en ligne (Stripe). L'admin voit bien ses sous.
3. Au bar, elle prend un café. **La caisse ne voit pas son FED** : la carte s'affiche
   « anonyme », le café tombe sur l'écran de complément.

## 2. La cause

La caisse ne lit et ne débite l'ancien Fedow que **par la signature de la personne** :
`lire_depensable_fed_frais(carte.user)` (`retrieve_by_signature`), puis
`_debiter_legacy(user, …)` (`to_place_from_qrcode`). Tous les appelants sont gardés par
`if carte.user is not None` (`laboutik/views.py` : check carte, paiement NFC, complément,
2ᵉ carte ; `controlvanne/billing.py` pour la tireuse). Sans `user` local, le FED vaut 0
**en silence**.

Or la carte de la personne n'a pas de `user` en local :

- **`ScanQrCode.link`** (`BaseBillet/views.py`) lie la carte chez Fedow. La réponse de
  Fedow (`linked_serialized_card`) contient tout ce qu'il faut pour créer la carte locale.
  Mais `CarteService.lier_a_user` cherche seulement une carte locale existante. Il lève
  `CarteIntrouvable`, et le code traite ce cas comme « ATTENDU… rien à réparer ».
- **Au premier scan**, `trouver_ou_rapatrier_la_carte` (`QrcodeCashless/services.py`)
  crée la carte **sans `user`**, alors que la fiche Fedow la dit liée
  (`is_wallet_ephemere: False`) et que le portefeuille local de la personne porte le
  même uuid. C'est le choix écrit dans `CHANTIER-02` §4.1 étape 6, avec une
  justification fausse : `obtenir_wallet_carte_depuis_fedow` ne pose jamais `user`.
- Plus rien ne répare ensuite. Refaire la liaison échoue côté Fedow (« déjà liée »).

### Lieu ancien ou lieu neuf ?

Le bug frappe **toute carte liée chez Fedow avant que Lespass l'ait en local**. Un lieu
ancien y est exposé à 100 % : la bascule en V2 refuse un lieu qui a des cartes locales
(raison 6 de `Customers/bascule_vers_v2.py`). Ses cartes sont donc forcément « Fedow
seulement ». Un lieu neuf dont les cartes sont créées dans l'admin Lespass n'est pas
touché, car la carte est locale dès sa création.

### Le même trou, seconde face : la carte anonyme qui porte du FED

L'ancienne borne avec TPE a crédité du FED sur le **portefeuille éphémère** de cartes
anonymes. Elle crédite le moteur local depuis le commit `f47023f4` du 2026-09-29. LaBoutik
V1 a fait de même. La caisse V2 ne lit ni ne débite ce FED : il n'y a pas de personne,
donc pas de signature.

Pourtant l'ancien Fedow sait le faire sans personne, comme LaBoutik V1 le faisait :
- **Lecture** : `GET card/{tag}/` (`NFCcard.retrieve`). Lespass l'utilise déjà pour la
  borne, le vidage et le rapatriement.
- **Débit** : `POST transaction/` (`TransactionW2W`, branche `SALE`,
  `Fedow/fedow_core/serializers.py:1288`). Il exige :
  - la carte du client ;
  - une **carte primaire déclarée chez Fedow pour le lieu** ;
  - une monnaie acceptée par le lieu.

  Aucune signature de la personne n'est demandée. Une place Lespass sans clé RSA de
  cashless est authentifiée par sa seule clé API (« extension S6 »,
  `Fedow/fedow_core/permissions.py:257`).
  Le client Lespass n'a pas cette méthode : `TransactionFedow.to_place` est à reprendre
  de `LaBoutik/fedow_connect/fedow_api.py:538`.

### Pourquoi les tests ne l'ont pas vu

Le détail complet est dans l'annexe. En bref :
1. **Des tests verrouillaient le bug comme une règle** : `test_20` du rapatriement,
   `test_carte_anonyme_pas_de_lecture_fed` (c1),
   `test_carte_anonyme_n_appelle_jamais_l_ancien_fedow` (tireuse), le test 37a. Ils
   traduisaient fidèlement des specs à l'hypothèse fausse (spec
   `FEDOW_IMPORT/11` §6 garde 1 : « carte anonyme → pas de FED »).
2. **Deux specs se contredisaient** : `FEDOW_IMPORT/11` §6bis étape 2 demandait de poser
   le `user` d'une carte liée, `QRCODECASHLESS/CHANTIER-02` §4.1 étape 6 a écrit
   l'inverse. Le test 20 a figé la seconde.
3. **Les fixtures sautent le parcours réel.** Toutes les cartes FED sont créées à la main
   avec `user=`, y compris dans l'E2E contre le vrai Fedow. Le test de la liaison QR
   (`test_vues_carte_branchees_sur_service.py`) crée la carte locale **avant** la liaison.
4. **Le faux Fedow du rapatriement** ne renvoie que des cartes anonymes.
5. **La spec du rapatriement a oublié la liaison QR** : `ScanQrCode` n'apparaît pas
   dans son inventaire des points d'entrée (§4.3).

## 3. Correction proposée (à valider)

### Décisions du mainteneur (2026-10-14)

Elles remplacent les propositions C-1 à C-4 ci-dessous là où elles diffèrent.

- **Tant que le modèle hybride V1/V2 tourne, tout lieu V2 a du FED à débiter** sur
  l'ancien Fedow (recharges en ligne et par TPE). Les cartes éphémères sont très
  utilisées en production : C-3 fait partie de ce chantier.
- **Un seul chemin, tout par la carte (option B).**
  - Lire : `NFCcard.retrieve(tag_id)` pour toutes les cartes, avec ou sans
    propriétaire. Fedow rend le portefeuille de la personne ou le portefeuille
    éphémère (`Card.get_wallet`). On ne garde que le FED de la fiche, et on ajoute
    les jetons locaux.
  - Payer : `POST transaction/` avec la carte client et une carte primaire. Le débit
    par la personne (`to_place_from_qrcode`) n'est plus utilisé en caisse ni à la
    tireuse.
- **Caisse** : la carte primaire est celle du caissier (`tag_id_cm`). Elle est déjà
  contrôlée chez Fedow à chaque ouverture (`_verifier_carte_primaire_aupres_de_l_ancien_fedow`).
- **Tireuse** :
  - elle prend la plus ancienne carte primaire du lieu ;
  - **elle ne se lance pas sans carte primaire**, dans tout lieu ;
  - **au badge, on contrôle aussi chez Fedow que cette carte est encore primaire**
    pour le lieu (`is_primary` de sa fiche). Si ce n'est pas le cas, on refuse de
    servir. Un débit refusé après le service, c'est de l'argent perdu.
- **Carte primaire V1 scannée à l'ouverture : on ne touche à rien.** Le rapatriement
  fabrique la carte, sans `CartePrimaire`, et invite à la déclarer dans l'admin
  (`QrcodeCashless/services.py:193`).
- **Pas de rattrapage des cartes primaires** : aucune n'existait avant la mise en
  production, et l'admin les déclare à l'ancien Fedow à leur création.
- C-1, C-2 et C-4 restent au programme.

### C-1 — Le miroir local d'une carte porte sa propriétaire

Dans `QrcodeCashless/services.py`, on extrait de `trouver_ou_rapatrier_la_carte` la
fabrication du miroir à partir d'une fiche Fedow :
`fabriquer_le_miroir_de_la_carte(fiche_fedow)`. Elle reprend les étapes 5 à 7 : refus
legacy, `Detail`, savepoint, origine du portefeuille. On y ajoute une règle :

- la fiche dit la carte **liée** (`is_wallet_ephemere: False`) → `carte.user` =
  `Wallet.objects.filter(uuid=fiche["wallet"]["uuid"]).first().user`
  (`TibilletUser.wallet` est un `OneToOneField`, `related_name="user"`) ;
- aucun utilisateur local ne porte ce portefeuille → carte sans `user`, journal
  `warning`, **jamais d'erreur au scan** ;
- carte **anonyme** → rien ne change.

Elle a deux appelants :
1. `trouver_ou_rapatrier_la_carte` (le premier scan) ;
2. `ScanQrCode.link` : sur `CarteIntrouvable`, on fabrique le miroir à partir de
   `linked_serialized_card`, sans nouvel appel réseau. Un refus `CarteDUnLieuNonMigre`
   est journalisé, et la liaison reste réussie côté Fedow. Le commentaire « ATTENDU »
   est réécrit.

### C-2 — Réparer les cartes déjà rapatriées en production

Une commande `manage.py relier_les_cartes_rapatriees`, en **passage à blanc par
défaut** et avec `--executer` pour écrire. Lieu par lieu (`tenant_context`, place
Fedow reliée), elle reprend les cartes `user=None` dont l'origine est le lieu, et appelle
`card_tag_id_retrieve(tag)`. Quand la carte est liée, elle pose le `user` du
portefeuille. Elle rend un compte rendu : reliées, sans utilisateur local, anonymes,
Fedow injoignable.

### C-3 — Carte anonyme : lire et débiter le FED par la carte

- **Lecture** : une brique `lire_fed_de_la_carte(carte)` → `(centimes, disponible)`. Elle
  lit `FedowAPI().NFCcard.retrieve(tag)` et additionne **le FED seulement** : un lieu V2
  n'émet ni n'accepte de monnaie locale legacy (raisons 3 et 5 de la bascule). Elle se
  dégrade en silence, comme `lire_depensable_fed_frais`. Elle sert quand `carte.user`
  est vide, partout où la caisse lit le FED.
- **Débit** : on reprend `TransactionFedow.to_place` de LaBoutik V1, avec la même
  signature : `amount`, `asset`, `wallet`, `user_card_firstTagId`,
  `primary_card_fisrtTagId`, `comment`, `metadata`.
  - Un débit = **une seule transaction**, sur le FED, depuis le portefeuille de la carte.
    Il n'y a donc pas de cascade côté client, et pas de débit partiel entre deux envois.
  - La forme rendue est celle de `_debiter_legacy` (`asset`, montant, `STRIPE_FED`,
    uuid), pour réutiliser `_repartir_legacy_sur_articles` et les règlements.
  - Carte primaire : `tag_id_cm` du formulaire de caisse.

### C-4 — Corriger les textes faux

- `controlvanne/billing.py:244` : « L'ancien Fedow ne débite que le portefeuille d'un
  UTILISATEUR ».
- Le commentaire « ATTENDU » de `ScanQrCode.link`.
- La docstring de `obtenir_wallet_carte_depuis_fedow`.
- Les specs `CHANTIER-02` §4.1 étape 6 et §8 test 20, ainsi que `FEDOW_IMPORT/11` §6
  garde 1 : y ajouter un renvoi vers ce chantier.

### Questions au mainteneur

| # | Question | Proposition |
|---|---|---|
| Q1 | C-3 : caisse ouverte par une session admin, **sans carte primaire** : que faire du FED d'une carte anonyme ? | L'afficher, ne pas le débiter, passer au complément avec un message « carte primaire requise » |
| Q2 | C-3 : la **tireuse** n'a pas de carte primaire Fedow. Débit par carte possible ? | Hors périmètre de ce chantier ; le test témoin de la tireuse est requalifié « limite, doit devenir rouge » |
| Q3 | C-1 : la personne a **déjà une autre carte** locale (anti-vol de `lier_a_user`), mais Fedow dit cette carte liée à elle. On pose quand même le `user` ? | Oui : Fedow fait foi sur le propriétaire ; on journalise |
| Q4 | L'« extension S6 » (permission par clé de place) est-elle **déployée sur le Fedow de production** ? | À vérifier avant C-3. Le vidage de carte en prod passe par la même permission |
| Q5 | Faut-il aussi lire et débiter **par la carte** les cartes liées, pour un seul chemin ? | Non : le chemin par signature marche et fait la cascade côté Fedow en une transaction |
| Q6 | C-1 : faut-il aussi poser `wallet_ephemere` au rapatriement d'une carte anonyme ? | Non, hors sujet : c'est déjà fait au premier paiement |

### Constat de l'audit, hors périmètre mais à traiter vite

D'après l'annexe, constat 3 : la vraie réponse de `qrcodescanpay` ne porte pas
`serialized_asset`. La catégorie est alors lue par `asset.retrieve` **après** le débit.
Si cette lecture échoue, la caisse répond « rescannez » (409) sans journal d'incident.
Le FED est débité sans vente, et un rescan peut débiter deux fois. **À vérifier par
la relecture**, puis à traiter dans un chantier séparé.

## 3 bis. Contre-expertise Fable (2026-10-14)

La relecture confirme le diagnostic : H1, H2, H3, H5, H6, H8, H9 et H10 sont CONFIRMÉES ;
H4, H7 et H11 sont NUANCÉES. Elle corrige l'assistant sur quatre points :

1. **Le contrôle `sender == portefeuille de la carte` existe chez Fedow.** Il est dans
   `Transaction.save()` (`Fedow/fedow_core/models.py:718-721`, par des `assert`), avant
   toute écriture de solde. Il n'y a pas de faille. Ce n'est simplement pas le bon
   étage : un échec donne un 500, pas un 400.
2. **LaBoutik V1 recharge en TLF, pas en FED.** Le FED sur un portefeuille éphémère ne
   vient **que du TPE de la borne**, par le webhook Fedow
   `terminal.reader.action_succeeded`
   (`validate_stripe_reader_wise_pose_and_make_transaction`).
3. **« Lieu neuf non touché » est faux.** Deux autres chemins créent le même état :
   - **la réconciliation de l'admin des cartes**, quand la carte est déjà connue de
     Fedow (`QrcodeCashless/admin.py:256-264`), crée un miroir sans `user` ;
   - **l'admin des adhésions** (`MembershipAddForm.save` →
     `lier_la_carte_a_l_adherent_chez_fedow`, `Administration/admin_tenant.py`) lie la
     carte **chez Fedow seulement**, jamais en local. La personne ne peut plus se
     réparer par `/qr/link`, que Fedow refuse (carte déjà liée).
4. **`GET /qr/<uuid>/` fait un 500** quand le portefeuille miroir existe sans `user`
   (`BaseBillet/views.py:671-673`). C'est l'état du témoin de C-1 (personne inconnue
   ici).

**Piège latent, pas actif aujourd'hui : le double crédit à la borne.** La borne V2
envoie toujours au PaymentIntent les métadonnées que lit le webhook TPE de Fedow
(`kiosk/models.py:236-248`). Depuis `f47023f4`, elle crédite en plus la TLF locale
(`kiosk/credit.py`, déclenché par `get_from_stripe`, pas par un webhook). Le code est
déployé (`origin/main`), mais le double crédit exige **toutes** ces conditions :

1. un lieu en moteur `v2` (`IsKioskTerminal` ferme la borne à un lieu legacy) ;
2. une place chez l'ancien Fedow (`FedowConfig.fedow_place_uuid`). Tout lieu V2 en a
   une dès son premier `FedowAPI()` (recharge en ligne, adhésion…) : `PlaceFedow`
   appelle `create_place()` quand `can_fedow()` est faux (`fedow_connect/fedow_api.py`).
   Seul un lieu qui n'a encore jamais parlé à Fedow envoie `"None"` ;
3. une borne appairée en rôle Kiosque (en prod, l'admin n'y accède pas par navigateur :
   `kiosk/views.py`, garde `DEMO or DEBUG`) ;
4. un lecteur WisePOS actif, enregistré chez Stripe et branché sur cette borne ;
5. le webhook Fedow abonné à `terminal.reader.action_succeeded` sur le compte racine ;
6. la carte connue de Fedow par son `tag_id`.

Selon le mainteneur (2026-10-14), aucune borne V2 n'est branchée en production : les
conditions 3 et 4 manquent, donc le risque est nul aujourd'hui. Il deviendra réel dès
qu'une borne sera branchée dans un lieu basculé, si rien ne change. À corriger avant :
retirer les métadonnées `fedow_place_uuid`/`tag_id` du PaymentIntent de la borne V2
(elle crédite en local), ou faire ignorer à Fedow les PaymentIntent d'une place Lespass
en moteur V2.

**Borne V2 fermée en attendant (décision du mainteneur, 2026-10-15).** Un lieu V2 pouvait
allumer `module_kiosk` d'un clic, et les routes de la borne ne lisaient pas ce module.
Désormais :
- `MODULES_EN_ATTENTE_D_ACTIVATION` (`Administration/admin/dashboard.py`) : la carte du
  kiosk éteint est grisée, sans interrupteur ; un kiosk resté allumé garde son
  interrupteur, pour l'éteindre ;
- `module_toggle` (`Administration/admin_tenant.py`) refuse de l'allumer, même par un
  POST direct ;
- `IsKioskTerminal` (`kiosk/views.py`) ferme les routes de la borne quand `module_kiosk`
  est éteint.
Tests : `tests/pytest/test_module_kiosk_en_attente.py`. Pour rouvrir la borne : vider
`MODULES_EN_ATTENTE_D_ACTIVATION`, après avoir corrigé le double crédit. Le test E2E C
(carte anonyme avec du FED) est en `xfail` « en attente de la borne (kiosk) V2 ».

**H7, à nuancer.** « Une seule transaction » repose sur le miroir local des fédérations
(`AssetFedowPublic`). C-3 doit donc tolérer plusieurs jetons : ne débiter que le FED,
ignorer le reste.

**H9 confirmée** : un FED peut être débité sans vente (catégorie lue après le débit, 409
sans journal d'incident), au paiement NFC, au complément et à la 2ᵉ carte. Parade sans
réseau : lire la catégorie dans le miroir local `AssetFedowPublic` d'abord. Il faut aussi
un journal d'incident dans l'`except`. **Chantier séparé.**

**Recommandation de Fable, reprise ici :**
- **Livrer d'abord C-1, C-2 et C-4.** Le diff est petit et il corrige la production.
  Corriger dans le même mouvement l'admin des adhésions (liaison locale) et la
  réconciliation de l'admin des cartes (poser le `user`). C-2 parcourt TOUTES les
  `CarteCashless(user=None, detail__origine=lieu)` : rien ne distingue une carte
  rapatriée.
- **Traiter C-3 dans un chantier séparé**, et y trancher entre « repli par la carte pour
  les cartes anonymes » et « chemin unique par la carte pour l'argent, comme V1 ». Le
  chemin unique est plus simple à tester, et la réponse SALE porte la catégorie (H9
  réglé). En contrepartie, la carte primaire devient obligatoire.
- Sur `IntegrityError` dans `link` (la caisse a créé la carte pendant la liaison),
  rappeler `lier_a_user` sur la carte existante.

**Ses réponses aux questions :**
- **Q1** : le FED d'une carte anonyme n'est compté que si une carte primaire déclarée
  est présente. Sinon la vente finirait en 409.
- **Q3** : oui, Fedow fait foi. Journal `warning`, jamais de refus.
- **Q4** : l'extension S6 est très probablement déployée (ouverture de caisse et
  rapatriement passent par la même permission). À confirmer en lisant le
  `permissions.py` déployé.
- **Q2, Q5, Q6** : d'accord avec les propositions.

**Défauts de tests relevés, et suites données :**
- Paiement anonyme facile à faire passer par une correction fausse → **ajout** de
  `test_carte_anonyme_au_fed_insuffisant_ne_compte_que_son_fed_et_passe_au_complement`
  (rouge : reste 2.00 au lieu de 1.00).
- Formes de jeton divergentes entre c1 et le nouveau fichier → **alignées** sur
  `TokenValidator`.
- `metadata` du débit par la carte non vérifiée → **ajoutée**.
- Restent à faire :
  - des `MagicMock` sans `spec` ;
  - des cas manquants : carte primaire absente, propriétaire inconnu ici sans 500 sur
    `/qr/<uuid>/`, course entre `/qr/link` et le scan, commande C-2, admin des
    adhésions ;
  - le marqueur `stripe_listen` de l'E2E, inutile pour la recharge FED.
- Préparation du test E2E C : Fable recommande **une commande de gestion côté Fedow**,
  réservée à `DEBUG`, qui crédite le FED d'une carte par le même code que le webhook
  TPE.

## 4. Les tests

### Rouges, écrits avant la correction (2026-10-14)

`tests/pytest/test_carte_liee_chez_fedow_fed_en_caisse.py` : **7 failed, 1 passed** (le
passé est un témoin), chacun pour la raison attendue. Le 8ᵉ test a été ajouté après la
relecture Fable (§3 bis). Avec le test c1 réécrit, cela fait 8 rouges au total.

| Test | Couvre | Rouge parce que |
|---|---|---|
| `test_rapatriement_d_une_carte_liee_chez_fedow_pose_sa_proprietaire` | C-1 | `user_id` vaut None |
| `test_rapatriement_d_une_carte_liee_a_un_portefeuille_inconnu_ici_reste_sans_proprietaire` | C-1, témoin | (vert) |
| `test_liaison_par_qrcode_d_une_carte_absente_en_local_la_cree_avec_sa_proprietaire` | C-1 | aucune carte locale |
| `test_check_carte_d_une_carte_liee_chez_fedow_seulement_affiche_son_fed` | bug de prod | carte affichée anonyme |
| `test_cafe_paye_en_fed_avec_une_carte_liee_chez_fedow_seulement` | bug de prod | écran de complément |
| `test_check_carte_d_une_carte_anonyme_affiche_le_fed_de_son_portefeuille` | C-3 | pas de pastille FED |
| `test_cafe_paye_en_fed_par_une_carte_anonyme_debite_par_la_carte_et_la_carte_primaire` | C-3 | écran de complément |

**Contrôle du harnais.** Avec une carte locale déjà liée (fichier temporaire, supprimé),
les deux tests de caisse d'une carte liée passent : 2 passed. Le rouge vient donc bien
du code, pas du test.

### Tests existants modifiés

| Fichier | Changement |
|---|---|
| `test_c1_solde_complet_carte.py` | `test_carte_anonyme_pas_de_lecture_fed` devient `test_carte_anonyme_lit_le_fed_de_sa_carte_sur_l_ancien_fedow` (rouge : `fed_disponible` vaut False) |
| `test_rapatriement_carte_fedow.py` | test 20 renommé `test_20_carte_anonyme_…`, avec une docstring qui le limite aux cartes anonymes |
| `test_tireuse_ancien_fedow.py` | docstring requalifiée « TÉMOIN D'UNE LIMITE, doit devenir rouge » ; l'affirmation fausse est retirée (Q2) |
| `test_caisse_ecrit_la_vente.py` | docstring de `creer_une_carte_nfc_d_un_membre_sans_solde_local` corrigée |

Fichiers voisins relancés : 178 passed, et les 7 rouges attendus.

### E2E

`tests/e2e/test_carte_liee_par_qrcode_fed_en_caisse.py` est écrit par un agent. Il
tourne contre le vrai Fedow et le vrai Stripe, familles `qrcode`, `caisse`, `monnaie`.
Lancement du 2026-10-14 : **2 failed, 1 passed**.

- **A — le parcours complet : ROUGE à l'étape 4.**
  - Les étapes 1 à 3 passent : liaison par QR, confirmation de l'email, Stripe réel,
    3 € de FED crédités.
  - Étape 4 : aucune carte locale après la liaison.
  - Étapes 5 à 8 : fiche « anonyme » à 0,00 €, écran de complément, FED inchangé
    (300 → 300), aucune pastille FED après le café.
- **B — témoin, ordre inverse : VERT.** Le check carte vient d'abord, puis la liaison
  par QR, puis la recharge, puis le café payé en FED (règlement SF de 150, vente
  REGLEE). **Le bug dépend donc de l'ordre.**
- **C — carte anonyme avec du FED legacy : ROUGE dès la préparation.** Ce rouge vient
  d'un `pytest.fail` explicite.
  - Le seul chemin qui pose du FED sur une carte anonyme est le webhook Stripe
    `terminal.reader.action_succeeded` de l'ancienne borne
    (`validate_stripe_reader_wise_pose_and_make_transaction`, côté Fedow).
  - Préparation à trancher :
    1. un vrai lecteur Terminal simulé, avec un second `stripe listen` dirigé vers
       Fedow ;
    2. une route de dev côté Fedow ;
    3. un shell dans `fedow_django`.

Constats de l'agent E2E :
- **`stripe listen` n'est pas nécessaire pour la recharge FED.** Le retour navigateur
  (`return_refill_wallet`) suffit. Le marqueur `stripe_listen` du fichier est à
  rediscuter.
- **Un helper probablement cassé.** Celui de recharge de `test_parcours_fedow_reel.py`
  cherche le bouton sur `/my_account/balance/`, qu'il a quitté avec le skin V2. Pas
  vérifié.
- **Chromium Playwright manquait** dans le conteneur. Il a été réinstallé.


## 5. Correction livrée (2026-10-14, non commitée)

Règle appliquée (mainteneur) : **lieu basculé en V2 = FED de l'ancien Fedow + jetons
locaux du Fedow V2 interne.** Lieu encore legacy = FED + jetons locaux de l'ancien
Fedow, mais par LaBoutik V1 et le paiement par QR code : la caisse V2, la borne et la
tireuse lui sont fermées par le verrou moteur.

### Code

| Fichier | Changement |
|---|---|
| `fedow_connect/fedow_api.py` | `TransactionFedow.to_place` : débit par la carte et une carte primaire (`POST transaction/`, SALE), repris de LaBoutik V1 |
| `laboutik/views.py` | `_jeton_fed_de_la_fiche` ; `lire_depensable_fed_frais(carte)` lit la fiche de la carte (FED seul) ; `_debiter_legacy(carte, tag_id_carte_primaire, montant, uuid)` : une transaction FED par la carte ; plus de garde `carte.user` (check carte, paiement NFC, complément, 2ᵉ carte) ; `_categorie_asset_transaction` supprimée |
| `laboutik/templates/laboutik/partial/hx_card_feedback.html` | « Réseau indisponible » pour toute carte |
| `controlvanne/billing.py` | `carte_primaire_de_la_tireuse` (la plus ancienne du lieu) ; le FED ne compte que si cette carte est confirmée par l'ancien Fedow (`_verifier_carte_primaire_aupres_de_l_ancien_fedow`) ; débit par la carte |
| `controlvanne/viewsets.py` | `authorize` : pas de carte primaire dans le lieu → la tireuse refuse |
| `QrcodeCashless/services.py` | C-1 : `proprietaire_d_apres_la_fiche_fedow`, `fabriquer_le_miroir_de_la_carte` (pose `user`), `relier_la_copie_locale_de_la_carte` |
| `BaseBillet/views.py` | `ScanQrCode.link` : copie locale liée ou fabriquée (`relier_la_copie_locale_de_la_carte`) |
| `Administration/admin_tenant.py` | adhésion dans l'admin : copie locale mise d'accord après `linkwallet_card_number` |
| `QrcodeCashless/admin.py` | réconciliation de l'admin des cartes : la propriétaire selon Fedow est posée |
| `QrcodeCashless/management/commands/relier_les_cartes_rapatriees.py` | C-2 : à blanc par défaut, `--executer` pour écrire |

Le débit par la personne (`to_place_from_qrcode`) reste pour le paiement en ligne par
QR code et `launch_payment`.

### Specs corrigées (C-4)

`FEDOW_IMPORT/11` §6 garde 1 et §6bis cas 3 ; `QRCODECASHLESS/CHANTIER-02` §4.1 étape 6.

### Tests

- Les 8 rouges du §4 et c1 : verts. Neuf : `tests/pytest/test_relier_les_cartes_rapatriees.py` (C-2).
- Tireuse : harnais passé à la carte ; fixture partagée
  `carte_primaire_du_lieu_confirmee_par_l_ancien_fedow` (`fabriques_controlvanne.py`) ;
  trois tests neufs (carte anonyme payée en FED, lieu sans carte primaire, carte primaire
  non confirmée). Le témoin « carte anonyme n'appelle jamais l'ancien Fedow » est remplacé.
- E2E `test_parcours_fedow_reel.py` : les deux tests de monnaie locale de l'ancien Fedow
  À LA CAISSE V2 sont supprimés (cas impossible dans un lieu V2) ; le test du FED utilise
  une carte neuve connue de l'ancien Fedow, la carte primaire déclarée, et attend `SAL`.

### Reste à faire / à décider

- **E2E encore bâtis sur une monnaie locale legacy émise par `lespass` (V2)** :
  `test_parcours_fedow_reel.py` (vente QR et remise en banque, relevé) et
  `test_federation_asset_legacy_inter_lieux.py`. Ils passent par le QR code, pas par la
  caisse V2, mais contredisent la règle : l'émetteur doit être un lieu legacy.
- Plus tard (jugé prématuré par le mainteneur) : carte primaire retirée chez Fedow en
  plein service ; reprise d'une réponse perdue par `last_transaction` ; `atomic()` sur la
  vente côté Fedow ; la carte primaire de la tireuse choisie par son point de vente.
- Double crédit latent de la borne V2 (§3 bis) : à corriger avant de brancher une borne.
