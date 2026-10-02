# Chantier 05-E — Un seul plan comptable, lisible, qui sépare tout

> **Statut** : 📝 **RÉÉCRITE le 2026-10-02** après relecture contre le code (SUIVI §4, ligne
> « E (relecture contre le code, avant brief) ») et réponses du mainteneur (SUIVI §5,
> 2026-10-02), **relue par Fable le 2026-10-02 et corrigée** (3 bloquants, 9 importants,
> SUIVI §4). Questions répondues le 2026-10-02 (§8). Version du 2026-09-28 :
> historique git.
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D10, D22, D23, D26, R2
> Effort : 3,5 j (3 sessions : E-1 §2-§3, E-2 §4-§5, **E-3 jetons §3.5**) — Dépend de : A
> (`hors_chiffre_affaires`) ; E-3 reprend du code des fiches B et D.
> Ses fonctions sont **utilisées par F** : aujourd'hui, les exports lisent
> `ClotureCaisse.rapport_json` (bâti sur `LigneArticle`), et une clôture couvre tout le
> lieu. E prépare le plan et les fonctions ; F les branche sur `Vente` / `Reglement`.
> **Migrations : oui** (`MappingMonnaie`, `PointDeVente.code_journal`, unicité du numéro de
> compte, retrait des deux modèles `comptabilite` et de leur migration de données,
> chargement du plan dans les lieux qui n'en ont pas).

## 1. Le besoin (mainteneur)

« On garde le plus complet et le plus agréable à lire, et on l'enrichit de ce qui manque.
Il faut arriver à dissocier les ventes en ligne, les points de vente, les monnaies, la
TVA. » Et (2026-10-02) : « Un seul [plan], simple, qui s'ouvre à la création du lieu et/ou
à la création des premières ventes s'il n'existe pas. »

| Pour séparer… | Outil | Exemple |
|---|---|---|
| la TVA | un compte par taux | 445710 (20 %) … |
| les moyens **et les monnaies** | un compte de trésorerie par moyen, **et un par monnaie** | espèces, CB, monnaie locale « Pêche » |
| les points de vente et le web | un **journal** par point de vente (colonne `JournalCode` du FEC) | `BAR`, `TIREUSE`, `WEB` |

## 2. Session E-1 — un seul plan, toujours présent

### 2.1 Ce qu'on garde, ce qu'on retire

- **On garde** les tables de la caisse : `laboutik.CompteComptable` (`laboutik/models.py`
  l.2007 : `numero_de_compte`, `libelle_du_compte`, `nature_du_compte`, `taux_de_tva`,
  `est_actif`) et `laboutik.MappingMoyenDePaiement` (l.2131 : `moyen_de_paiement` unique,
  `compte_de_tresorerie` nullable). Reliées aux catégories par
  `CategorieProduct.compte_comptable` (`BaseBillet/models.py` l.1154).
- **`numero_de_compte` devient unique** dans un lieu, en trois migrations séparées
  (PIEGES 9.113) : (1) `RunPython` de **dédoublonnage** (par numéro, garde le premier,
  repointe `CategorieProduct.compte_comptable` et `MappingMoyenDePaiement.compte_de_tresorerie`
  sur lui, supprime les autres ; rien dans le schéma `public`) ; (2) la contrainte ;
  (3) le chargement du plan (§2.2).
- **On retire** `comptabilite.CompteComptable` et `comptabilite.MappingMoyenDePaiement`
  (`comptabilite/models.py` l.149, l.196), leur admin (`comptabilite/admin.py` l.342,
  l.370) et **leur migration de données** (`comptabilite/migrations/0002`, `RunPython` qui
  pose 9 comptes et 13 correspondances) : « en prod, aucun compte comptable n'existe »
  (mainteneur) — **aucune recopie**. Leur seul lecteur (`comptabilite/csv_comptable.py`)
  lit désormais le plan de la caisse.

### 2.2 Un plan par défaut, chargé tout seul

- **Un seul plan par défaut**, aux numéros du plan comptable général à **6 chiffres**
  (§3.4) ; les deux profils actuels (`bar_resto`, `association`) disparaissent
  (mainteneur, 2026-10-02).
- **Une seule migration de données** charge le plan par défaut dans tout lieu qui n'a
  **aucun** compte. Elle couvre aussi la **création d'un lieu** : `Client.auto_create_schema
  = True` (`Customers/models.py` l.33) rejoue toutes les migrations dans un schéma neuf ;
  **aucun autre crochet** n'est nécessaire. Elle crée les comptes par `apps.get_model`
  et n'importe du chargeur que la **liste de données** (pas de modèle vivant).
- **Filet** (secours seulement) : un rapport, un export ou « Plan complet ? » qui ne
  trouve aucun compte charge le plan avant de continuer, de façon **idempotente**
  (`get_or_create` par `numero_de_compte` dans un `atomic`, `IntegrityError` attrapée :
  deux exports simultanés ne cassent rien). Rien sur le chemin de la caisse.
- **Bug existant corrigé** : le bouton « Charger un plan » de l'admin (`laboutik/views.py`
  l.4176-4210, `reset = nb_existants > 0` l.4203) **efface tout le plan** quand des
  comptes existent, et les liens des catégories passent à vide (`SET_NULL`), alors que son
  bandeau (`Administration/templates/admin/comptable/changelist_before.html` l.16) dit
  l'inverse. Désormais il **ajoute ce qui manque**, sans rien effacer ni renuméroter.
- Le chargeur **relie** les catégories qu'il crée (« Financement participatif », écarts
  D26, §3.3) à leur compte.

## 3. Session E-1 — les règles de compte

### 3.1 Le compte d'un règlement : `compte_pour_reglement(moyen, asset_uuid)`

1. le compte de la **monnaie** (`laboutik.MappingMonnaie`, nouveau) s'il existe ;
2. sinon, **seulement** si le règlement n'a pas de monnaie (espèces, CB, Stripe…) ou si
   la monnaie est **celle du lieu** : le compte du **moyen** (`MappingMoyenDePaiement`) ;
3. sinon **erreur explicite** (D23). **Un compte par monnaie** (mainteneur, 2026-10-02) :
   une monnaie d'un autre lieu (TLF fédérée, réglée en `LE` avec l'uuid distant) sans
   compte bloque l'export, et « Plan complet ? » le dit.

`SF` (règlements FED : ancien Fedow `laboutik/views.py` l.1789, vidage l.1992 / l.2009,
tireuse) passe **toujours** par la monnaie : le chargeur relie les **deux uuid du FED**
(`fedow_core` et ancien Fedow) au 467000. Aucune correspondance de moyen pour `SF`.

`MappingMonnaie` : `asset_uuid` (unique, **sans FK** : la monnaie vit dans
`fedow_core.Asset` **ou** dans `fedow_public.AssetFedowPublic` pour l'ancien Fedow), et
`compte_de_tresorerie` (FK `CompteComptable`). « Monnaie du lieu » :
`fedow_core.Asset.tenant_origin` = le lieu, ou `AssetFedowPublic.origin` = le lieu.

Moyens sans écriture d'argent : `NA` (FREE / OFFRIR), `NM` (points). `LG` (jetons offerts)
**a une écriture** (D8 bis, §3.5) : son règlement solde la dette au 419100.

### 3.2 Le journal : `journal_pour(point_de_vente, origine)`

- **Le point de vente gagne toujours** quand il existe, quelle que soit l'origine (une
  tireuse a son point de vente : son code, pas `TIREUSE`).
- `PointDeVente.code_journal` : `CharField(max_length=10, blank=True)`, **lettres
  majuscules seules** (le profil PennyLane de `laboutik/profils_csv.py` l.118 n'accepte
  que des lettres). Vide → **dérivé du nom** (majuscules, sans accent, lettres seules, 10
  caractères). Deux points de vente qui donnent le même code : « Plan complet ? » le
  signale et l'export est refusé (D23). (Démo : aucune collision ; chaque tireuse crée son
  point de vente à son nom, `controlvanne/signals.py` l.255.)
- Sans point de vente, selon l'origine (`SaleOrigin`, `BaseBillet/models.py` l.79-88, 9
  codes au 2026-10-02, inchangés) :

| Origine | Journal |
|---|---|
| `LB`, `QR`, `NF` (comptoir, point de vente inconnu) | `CAISSE` |
| `TI` | `TIREUSE` |
| `LP`, `AP`, `EX`, `WK` | `WEB` |
| `AD` | `ADMIN` |

Une origine non listée (ajoutée plus tard) lève une erreur ; un test le vérifie.

### 3.3 Le compte d'un article : `compte_pour_article(ligne)`

Règle, dans l'ordre :

0. **Article `hors_chiffre_affaires`** (recharges, écarts D26) : la catégorie de caisse
   est **ignorée** (une recharge rangée dans une catégorie 7xx irait sinon au chiffre
   d'affaires) ; on prend directement :
   - écarts : par leur nom constant (`NOM_ECART_RECU_EN_PLUS` → 758000,
     `_EN_MOINS` → 658000) ;
   - `RE` / `RC` (caisse), `R` / `E` (recharges en ligne) → 419100 ;
   - `VR` virement du pot central → **le compte de la monnaie de l'article**
     (`MappingMonnaie[ligne.asset]`, 467000 pour le FED) : le virement bancaire (débit
     512000, par le règlement `TR`) **solde la créance réseau** (mainteneur, 2026-10-02 :
     « que le token fédéré soit à l'équilibre avec le virement du pot central »).
1. `CR` retour de consigne : le compte de la **vente de la consigne**
   (`produit.consigne_remboursee`, sa catégorie) — le retour reflète la vente (D11).
2. la **catégorie de caisse** du produit (`Product.categorie_pos`) a un compte → ce compte
   (le lien passe par la **FK**, plus par le nom de la catégorie comme
   `laboutik/ventilation.py` l.47-57 : à reprendre en F) ;
3. sinon, par le **mode de caisse** (`Product.methode_caisse`, constantes l.1363-1373) :
   `AD` adhésion → 756000 ; `BI` billet → 706000 ; `VT` / `FR` → la catégorie est exigée ;
   `TM` (désactivé à la caisse, `laboutik/views.py` l.688) et `FD` (inutilisé) : erreur
   s'ils apparaissent ;
4. sinon, par le **type de produit** (`Product.categorie_article`, choix actifs
   l.1270-1286) : `B`, `F`, `G`, `Q`, `C` → 706000 ; `A` → 756000 ; `U`, `N` : la catégorie
   est exigée ; (`D` n'est créé nulle part : le prix libre passe par `Price.free_price`) ;
5. sinon **erreur explicite** (refus d'export, D23), signalée par « Plan complet ? ».

Ces numéros sont une constante `COMPTE_PAR_DEFAUT` du module du plan comptable,
recherchée par `numero_de_compte` (unique, §2.1). Un lieu qui veut un autre compte pose
une catégorie de caisse (mécanisme existant) ; l'aide le dit : « ajoutez des comptes, ne
renumérotez pas ceux du plan par défaut ».

**Vidage de carte** (`VC`, D12) : vente `VIDAGE_CARTE` **sans article** ; ses règlements
(+`LE` / +`SF`, −`CA`) suffisent (débit 419100 / 467000, crédit 530000). `VC` n'a pas de
compte d'article.

**Recharge offerte** (cadeau `RC` à la caisse, recharge cadeau `R` de l'API v2 réglée
FREE) : l'article est **entièrement offert** (`total_ttc = 0`, `part_offerte` =
total). L'écriture **charge + dette** (D8 bis) porte sur **`part_offerte`** : débit
**623400 cadeaux à la clientèle**, crédit 419100. La fiche F §4 ajoute cette ligne
(aujourd'hui elle ne crédite les articles hors CA que de Σ `total_ttc`, qui vaut 0).

**Crowds = don, sans TVA** (mainteneur, 2026-10-02) : produit système `categorie_article
= N` (`crowds/views.py` l.145), trouvé par son nom ; on ne change pas ce type. Il reçoit
une catégorie de caisse « Financement participatif » reliée au **754000** ; les lignes
crowds passent en **TVA 0** (aujourd'hui elles portent la TVA du produit ou du lieu,
`crowds/views.py` l.973 : à corriger en E-3). Une catégorie de caisse ne fait pas
apparaître un produit à la caisse (la caisse lit `point_de_vente.products` filtré sur
`methode_caisse`, `laboutik/views.py` l.672-679). 754 et 756 sont des comptes du plan
associatif (ANC 2018-06) : l'aide le dit (un bar en société mettra ses comptes 706 / 707).

**Écarts d'encaissement** (D26, déjà codés en D) : `tarif_vendu_d_ecart_d_encaissement`
(`BaseBillet/services_vente.py`) crée les catégories ; le chargeur les relie à 758000 /
658000. Les tests importent la constante des noms au lieu de la recopier
(`test_en_ligne_ecrit_la_vente.py` l.1656-1657).

### 3.4 Le plan par défaut (chargeur)

Numéros à 6 chiffres (validés par le mainteneur, 2026-10-02), sans renuméroter ce qui
existe déjà dans un lieu. Le compte de TVA est toujours cherché **par taux**, jamais par
numéro.

| Nature | Comptes |
|---|---|
| Ventes | 706000 prestations, 707000 marchandises (bar), **707900 ventes réglées en jetons offerts, hors TVA**, 756000 cotisations, 754000 dons (crowds) |
| TVA collectée | 445711 (20 %), 445712 (10 %), 445713 (5,5 %), 445714 (2,1 %) |
| Trésorerie | 530000 espèces, 511200 chèques, 512100 CB (TPE), **517100 Stripe** (fonds en attente de virement : `SN`, `SP`, `SR`), 512000 banque (virements `TR`, dont le pot central), 467000 réseau fédéré (FED, ses deux uuid) |
| Tiers | 419100 avances clients (recharges, monnaie locale du lieu, jetons offerts, D10, D8 bis) ; **471000 compte d'attente** (moyen `UK`, webhook de l'ancienne caisse) |
| Charges | **623400 cadeaux à la clientèle** (recharges offertes, D8 bis) |
| Écarts | 758000 (reçu en plus), 658000 (reçu en moins) |

Correspondances de moyens : `CA` → 530000, `CH` → 511200, `CC` → 512100, `SN` / `SP` / `SR`
→ 517100 (aujourd'hui `SP` / `SR` n'ont **aucune** correspondance, et `QR` / `SN` pointent
vers 51120001 / 512000), `TR` → 512000, `LE` → 419100, **`LG` → 419100** (D8 bis), `UK` →
471000 ; `NA`, `NM` : aucune écriture ; `SF` : par la monnaie (§3.1). `QR` est retiré des
**correspondances du chargeur** (aucun règlement ne le porte) ; l'énumération
`PaymentMethod.QRCODE_MA` reste (demandes de paiement QR, `BaseBillet/views.py` l.2068).
« Plan complet ? » rappelle les règlements au 471000 : « n règlements au compte
d'attente, à reclasser ».

### 3.5 Session E-3 — les jetons offerts soldent leur dette (D8 bis)

Décision du mainteneur (2026-10-02, tronc **D8 bis, qui remplace D8**) : « solder la dette,
voir le compte, avec une écriture sur les ventes, mais hors TVA ; jeton dépensé et crédité
visible par le lieu ». Ses suites (mainteneur, 2026-10-02) : ventes réglées en jetons au
**707900** ; jetons **perdus** (brûlés au vidage, périmés) : **la dette est annulée**
(débit 419100, crédit 623400).

**Les écritures** :

- recharge offerte : débit 623400, crédit 419100, sur `part_offerte` (§3.3) ;
- jeton dépensé (règlement `LG`) : l'article est une **vente ordinaire** (net = total,
  part offerte 0, **TVA 0**), au **707900** quelle que soit sa catégorie ; le règlement
  `LG` est un vrai règlement (deuxième égalité comprise), au **débit du 419100** ;
- jetons brûlés au vidage (D12 : aujourd'hui **aucun règlement** ne les écrit) : le vidage
  écrit leur montant pour que l'écriture débit 419100 / crédit 623400 existe (la forme est
  fixée au brief E-3, avec test) ; jetons périmés : seulement si un mécanisme d'expiration
  existe (à vérifier au brief ; sinon rien).

**Le code commité à reprendre** (session E-3, tests vus rouges, mutations) :

- la **caisse** (fiche B) : la part en jetons de la cascade s'écrit aujourd'hui avec
  `part_offerte` = total, `source_offert = JETONS` (`laboutik/views.py`
  `_creer_lignes_articles_cascade`) ;
- la **tireuse** : même logique (`controlvanne/billing.py` l.638-641) ;
- le **taux de TVA par moyen** `_taux_tva_de_la_ligne_de_caisse` (`laboutik/views.py`
  l.6213-6218) : aujourd'hui seuls `FREE` et `NM` rendent 0 ; **ajouter `LG` → 0** (sinon
  la bière en jetons porte de la TVA) ;
- le **service** : `MOYENS_OFFERTS` (`services_vente.py` : `LG`, `FREE`) : `LG` en sort ;
- les **avoirs** (fiche D) : une part payée en jetons n'est plus « entièrement offerte »
  (`ligne_entierement_offerte`, `ajouter_l_article_d_avoir`, `services_vente.py`
  l.590-686) ; elle est reconnue par `payment_method == LG` (jusqu'à H) : **pas** de champ
  « Remboursé par », un règlement `LG` **négatif** (avec `asset` / `carte` recopiés),
  **aucun recrédit de la carte** (tronc §9) : la dette revient sans que les jetons
  reviennent ;
- l'**archive LNE** : `laboutik/archivage.py` l.175-184 (HT recalculé sur le net) ;
- la **démo** : `Administration/management/commands/_demo_data_v2_ventes.py` l.604-610
  (lignes `LG` en TVA 5,5 sans vente) ;
- les **crowds** : TVA 0 (§3.3) ;
- la **fiche F** (à mettre en cohérence avant de l'ouvrir) : `LG` n'est plus « hors
  argent » (F §1), la section « Offerts » perd les jetons (F §2), F §4 écrit les jetons
  et la recharge offerte ; la bière en jetons **entre dans le chiffre d'affaires**
  (TTC = HT, TVA 0) ; la réconciliation « argent reçu » **exclut** `LG` (aucun euro
  n'entre) ; tests F 3, 4, 24 ;
- la **fiche R** (reprise) : la part en jetons s'écrit en D8 bis (§4.1-4.2 réécrits) ;
- les **tests** à reprendre (liste au brief E-3) : `test_caisse_ecrit_la_vente.py`,
  `test_tireuse_ecrit_la_vente.py`, `test_avoirs_ecrivent_la_vente.py`, `fabriques_vente.py`,
  `test_tireuse_ancien_fedow.py`, `tests/e2e/test_parcours_fedow_reel.py`,
  `test_demo_data_ventes.py`, `test_caisse_anciens_rapports.py` (fige « TVA des jetons à
  0 » par l'ancien chemin), `test_total_ht_ligne.py`, `test_hors_argent_offerts.py`, et
  les tests de caractérisation de la caisse (A′) ; tout changement d'attente est une
  conséquence de D8 bis (CHANGELOG).

**Ventes déjà scellées** : sortir `LG` de `MOYENS_OFFERTS` fait échouer
`verifier_chaine_ventes` (`laboutik/integrity.py` l.361, l.429 : relit la deuxième égalité
avec la liste courante) sur les ventes de test déjà scellées avec des jetons. Décision du
mainteneur : **régénérer la base de dev** après E-3 (aucun script de purge). Les tests qui
fabriquent ces ventes le font dans leur propre schéma ou `django_db`.

## 4. Session E-2 — lisible pour un bénévole

- Menu « Ventes & comptabilité » (`Administration/admin/dashboard.py` l.827-895) : « Plan
  comptable », « Comptes des moyens de paiement », « Comptes des monnaies », sous les
  rapports (les écrans de la caisse existent, `Administration/admin/laboutik.py`
  l.1795-1900, mais ne sont pas au menu).
- Liste des comptes **regroupée par nature**, une phrase d'aide par nature.
- « Comptes des monnaies » : une ligne par monnaie **acceptée par le lieu** (fedow_core
  `AssetService.obtenir_assets_accessibles`, **et** les monnaies de l'ancien Fedow
  `fedow_public.AssetFedowPublic`) ; une monnaie sans compte est signalée en orange
  (« l'export comptable sera refusé tant que ce compte manque »).
- Composant **« Plan complet ? »** en tête de page : ce qui manque pour exporter (produit
  vendu sans compte, moyen utilisé sans compte, monnaie sans compte, taux de TVA sans
  compte, collision de codes journal). Aucun équivalent n'existe aujourd'hui (les
  avertissements de `generer_fec` sont jetés, `Administration/admin/laboutik.py`
  l.1580-1588).
- Champ « prix d'achat » (`BaseBillet/models.py` l.1452) : `help_text` « en centimes, par
  unité de vente (kg, litre, pièce) ; 0 = inconnu » (D21).

## 5. Tests

Fichier : `tests/pytest/test_plan_comptable_unique.py`, **schéma dédié** (la migration
aura déjà chargé le plan du lieu de test) ; E-3 : fichiers de la caisse, de la tireuse et
des avoirs.

| # | Test |
|---|---|
| 1 | `test_compte_de_la_monnaie_prioritaire_sur_le_moyen` |
| 2 | `test_monnaie_du_lieu_sans_compte_repli_sur_le_moyen` (fedow_core **et** ancien Fedow) |
| 2b | `test_monnaie_d_un_autre_lieu_sans_compte_refus` |
| 2c | `test_fed_ses_deux_uuid_vont_au_467` (règlement `SF`) |
| 3 | `test_ni_monnaie_ni_moyen_erreur_explicite` |
| 4 | `test_moyens_hors_argent_sans_ecriture` (`NA`, `NM`) |
| 5 | `test_journal_du_point_de_vente_lettres_seules` (et le point de vente gagne sur l'origine) |
| 6 | `test_journal_par_defaut_selon_origine` (les neuf origines ; une inconnue → erreur) |
| 7 | `test_code_journal_collision_signalee` |
| 8 | `test_compte_article_ordre_des_regles` (recharge avec catégorie 7xx → 419100 ; `CR` → compte de la consigne ; bar par catégorie ; `AD` ; billet sans catégorie → 706000 ; recharge API v2 ; crowds → 754000 ; `VR` → compte de sa monnaie) |
| 8b | `test_compte_article_sans_regle_refus` (`N` / `VT` sans catégorie, `TM`, `FD`) |
| 8c | `test_recharge_offerte_charge_et_dette_sur_la_part_offerte` |
| 9 | `test_ecarts_758_et_658` |
| 10 | `test_migration_charge_le_plan_si_aucun_compte` (la fonction de la migration, pas un vrai lieu) et `test_filet_charge_le_plan_une_seule_fois` |
| 11 | `test_recharger_le_plan_n_efface_rien` (bug du bouton) |
| 12 | `test_tva_cherchee_par_taux` |
| 13 | `test_csv_comptable_lit_le_plan_de_la_caisse` |
| 14 | `test_dedoublonnage_des_numeros_de_compte` |
| 15 | `test_plan_complet_signale_ce_qui_manque` (dont le rappel du 471000) |
| E-3 | `test_jeton_depense_vente_au_707900_tva_zero`, `test_avoir_d_une_part_en_jetons_reglement_lg_negatif_sans_rembourse_par`, `test_jetons_brules_au_vidage_ecrits`, `test_crowds_tva_zero`, `test_tireuse_jetons_vente_ordinaire` |

Vus rouges : tous. Mutations : ordre monnaie / moyen inversé ; repli sur le moyen pour
toute monnaie ; journal toujours `WEB` ; collision non signalée ; catégorie avant la règle
« hors chiffre d'affaires » ; un seul compte pour les deux écarts ; bouton qui efface
encore ; TVA cherchée par numéro ; `LG` laissé dans `MOYENS_OFFERTS` ; TVA des jetons non
nulle ; avoir de jetons avec « Remboursé par ».

## 6. Tests existants à réécrire

| Fichier | Pourquoi |
|---|---|
| `tests/pytest/test_comptabilite_models.py` | fige le seed `comptabilite/0002` (l.62-90), retiré : supprimé, cas utiles repris |
| `tests/pytest/test_comptabilite_csv_comptable.py` | dépend du seed `0002` : crée des `laboutik.CompteComptable` |
| `tests/pytest/test_export_comptable.py` | compte 16 / 10 comptes (l.270, l.286) : nouveaux décomptes ; **exige `000000` dans le FEC** (l.467-470), contraire à D23 : attendre un refus |
| `tests/pytest/test_profils_csv_comptable.py`, `test_hors_argent_offerts.py`, `test_vente_en_points.py` | numéros des profils : relire après le plan par défaut |

Vérifier au démarrage : `rg -n "comptabilite.models import .*Compte|MappingMoyenDePaiement|charger_plan_comptable|51120001|000000" tests/`.

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-E-plan-comptable.md` (migrations oui ;
chaînes i18n : menus, aides par nature, messages de « Plan complet ? »).

## 7. Hors fiche E

- Les **exports** (FEC, CSV) restent branchés sur `ClotureCaisse.rapport_json` jusqu'à F,
  qui les passe sur `Vente` / `Reglement` et utilise les fonctions de E.
- Recharge du **kiosque** par le Stripe Terminal (aujourd'hui moyen `CC`, compte CB TPE) :
  kiosque hors chantier (TODO priorité kiosque).
- TODO `COMPTABILITE-inter-tenants.md` : `MappingMonnaie` remplace son `MappingAsset` ; il
  créditait la monnaie émise au 165, le tronc (D10) la met au 4191 : à reprendre dans ce
  TODO, pas ici.

## 8. Réponses du mainteneur (2026-10-02)

- **Q1 — Jetons** : solder la dette, écriture sur les ventes, **hors TVA** ; jeton dépensé
  et crédité visible par le lieu → D8 bis, §3.5.
- **Q2 — Plan** : un seul plan par défaut à 6 chiffres.
- **Q3 — Compte des cadeaux** : 623400 (défaut retenu, non contesté ; à confirmer à la
  relecture de la fiche).
- **Q4 — Chargement** : création du lieu + migration des lieux existants + filet au
  rapport / export ; rien pendant une vente.
- **Q5 — `VR`** : débit 512000, crédit 419100.
- **Relecture Fable (2026-10-02), réponses** : `VR` → débit 512000, crédit **le compte de
  la monnaie** (467000 pour le FED) ; ventes réglées en jetons au **707900** (hors TVA) ;
  jetons perdus : **dette annulée** (débit 419100, crédit 623400) ; **crowds = don, TVA
  0** ; ventes de dev scellées avec jetons : **régénérer la base de dev** après E-3 ;
  numéros validés (623400, 445711-445714, 707900).
