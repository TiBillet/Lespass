# Chantier 05-E — Un seul plan comptable, lisible, qui sépare tout

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28) — relue Fable + Opus, corrigée
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D22, D23, D26, R2
> Effort : 1,5 j — Dépend de : rien (indépendante de A-D : ses fonctions prennent un point
> de vente, une origine, un moyen, une monnaie, une ligne — pas une `Vente`).
> **Migrations : oui** (`MappingMonnaie`, `PointDeVente.code_journal` nullable, retrait des
> deux modèles `comptabilite`), sans `RunPython`.

## 1. Le besoin (mainteneur)

« On garde le plus complet et le plus agréable à lire, et on l'enrichit de ce qui
manque. Il faut arriver à dissocier les ventes en ligne, les points de vente, les
monnaies, la TVA. »

Trois outils classiques de la comptabilité française suffisent :

| Pour séparer… | Outil | Exemple |
|---|---|---|
| la TVA | un compte par taux (existe) | 44571x selon le taux |
| les moyens **et les monnaies** | un compte de trésorerie par moyen, **et un par monnaie** | espèces, CB, monnaie locale « Pêche » |
| les points de vente et le web | un **journal** par point de vente (colonne `JournalCode` du FEC) | `BAR`, `TIREUSE`, `WEB` |

## 2. Ce qu'on garde, ce qu'on retire

- **On garde les tables de la caisse** : `laboutik.CompteComptable` (`laboutik/models.py`
  ~l.1993 : numéro, libellé, nature, taux de TVA, actif) et
  `laboutik.MappingMoyenDePaiement` (~l.2117). Elles sont déjà reliées aux catégories
  (`CategorieProduct.compte_comptable`, `BaseBillet/models.py` ~l.1154) et utilisées par
  le FEC caisse. **On ne déplace pas les tables** : elles sont **affichées** dans
  « Ventes & comptabilité ».
- **On retire** `comptabilite.CompteComptable` et `comptabilite.MappingMoyenDePaiement`
  (`comptabilite/models.py` ~l.149, ~l.196) et leur admin (`comptabilite/admin.py`
  ~l.343, ~l.371) — ils n'ont pas de données initiales. Leur seul lecteur
  (`comptabilite/csv_comptable.py`) lit désormais le plan de la caisse. C'est **ici**
  que le deuxième plan comptable disparaît (pas en H).

## 3. Ce qu'on ajoute

### 3.1 Un compte par monnaie (`laboutik.MappingMonnaie`, nouveau)

| Champ | Sens |
|---|---|
| `asset_uuid` | uuid de la monnaie (`fedow_core.Asset`, SHARED_APPS : pas de FK), unique ; le nom se lit dans `Asset` |
| `compte_de_tresorerie` | FK `CompteComptable` |

`compte_pour_reglement(moyen, asset_uuid)` :

1. le compte de la **monnaie** (`MappingMonnaie`) s'il existe ;
2. sinon, **seulement** si le règlement n'a pas de monnaie (espèces, CB, Stripe…) ou si
   la monnaie est **celle du lieu** (`Asset.tenant_origin` = le lieu) : le compte du
   **moyen** (`MappingMoyenDePaiement`) ;
3. sinon **erreur explicite** (jamais de ligne sautée : D23). Une monnaie d'un **autre**
   lieu (TLF fédérée enregistrée `LE`, `laboutik/views.py` ~l.1396) ou la monnaie
   fédérée (`SF`) exige son propre compte : sans lui, elle partirait en silence au 4191
   du lieu.

Moyens sans écriture (hors argent) : `NA` (FREE / OFFRIR), `LG` (jetons), `NM` (points).

Le TODO `COMPTABILITE-inter-tenants.md` prévoyait `comptabilite.MappingAsset` avec un
rôle émetteur / commerçant : `MappingMonnaie` le remplace ; le rôle se déduira de la
monnaie (lieu d'origine) quand le TODO sera traité. Le signaler dans le TODO à ce
moment-là.

### 3.2 Un journal par point de vente

- `PointDeVente.code_journal` : `CharField(max_length=10, blank=True)`, **une seule
  migration**, aucune valeur remplie. `journal_pour` prend le code s'il est renseigné,
  sinon le **dérive du nom** (majuscules, sans accent, 10 caractères). Deux PV qui
  donnent le même code : signalé par « Plan complet ? » et refus d'export (D23) ;
  l'admin renseigne alors un code à la main (validé : lettres, chiffres).
- `journal_pour(point_de_vente, origine)` : le code du point de vente (renseigné ou
  dérivé) s'il y a un point de vente, sinon selon l'origine (`SaleOrigin`,
  `BaseBillet/models.py` ~l.79-88) :

| Origine | Journal par défaut |
|---|---|
| `LABOUTIK` (`LB`), `QRCODE_MA` (`QR`), `NFC_MA` (`NF`) (vente au comptoir, point de vente inconnu) | `CAISSE` |
| `TIREUSE` (`TI`) | `TIREUSE` |
| `LESPASS` (`LP`), `API` (`AP`), `EXTERNAL` (`EX`), `WEBHOOK` (`WK`, renouvellement d'abonnement Stripe) | `WEB` |
| `ADMIN` (`AD`) | `ADMIN` |

Ces neuf codes sont **tous** les `SaleOrigin` au 2026-09-28. Une origine non listée
(ajoutée plus tard) lève une erreur explicite ; un test le vérifie.

### 3.3 Le compte d'un article (`compte_pour_article(ligne)`)

Aujourd'hui, la caisse cherche le compte par la catégorie de caisse
(`Product.categorie_pos.compte_comptable`, `laboutik/ventilation.py` ~l.160), et le FEC
en ligne par le type de produit, en dur (`comptabilite/fec.py` ~l.127-150). Les
billets, adhésions, crowds, booking et la recharge API v2 n'ont **pas** de
`categorie_pos`. Règle unique :

1. la catégorie de caisse du produit a un compte → ce compte ;
2. sinon, le compte **par défaut du type de produit** (`Product.categorie_article`),
   donné par une **constante** `COMPTE_PAR_TYPE_DE_PRODUIT` (module du plan comptable,
   `laboutik/ventilation.py`) : un numéro de compte par type, résolu dans le plan du
   lieu par `CompteComptable.objects.get(numero=…)`. Pas de table, pas d'admin : un lieu
   qui veut un autre compte pose une catégorie de caisse sur le produit (mécanisme
   existant). Numéro absent du plan → erreur D23, signalée par « Plan complet ? » :

| Type de produit (`categorie_article`) | Compte par défaut (numéro du chargeur) |
|---|---|
| `BILLET` (B), `FREERES` (F), `BADGE` (G), `QRCODE_MA` (Q), `RESOURCE` (C, booking) | 706 prestations |
| `ADHESION` (A) | 756 cotisations |
| `DON` (D, prix libre en ligne) | 754 dons |
| `RECHARGE_CASHLESS` (R), `RECHARGE_CASHLESS_FED` (E) | 4191 avances clients |
| `FUT` (U), `NONE` (N) | pas de défaut : la catégorie de caisse est exigée |

**Crowds** : son produit système est créé avec `categorie_article = NONE`
(`crowds/views.py` ~l.194 ; le commentaire ~l.153 explique que ce type évite un
déclencheur). On ne change **pas** ce type. Le produit reçoit à sa création une
catégorie de caisse « Financement participatif » (créée à la demande, reliée au compte
des dons par le chargeur) ; le chargeur la pose aussi sur les produits crowds déjà
créés. Vérifier au démarrage qu'une catégorie de caisse ne fait pas apparaître le
produit à la caisse (un produit n'y apparaît que par les produits d'un point de vente).

3. sinon **erreur explicite** (refus d'export, D23), signalée par « Plan complet ? ».

**Écarts d'encaissement** (D26, fiche D) : deux catégories de caisse créées à la
demande, « Écart d'encaissement — reçu en plus » → **758**, « Écart d'encaissement —
reçu en moins » → **658**. Leurs noms sont une constante unique partagée par le
service de vente (fiche D) et le chargeur.

### 3.4 Les comptes de base (seed)

Le seul chargeur existant est `laboutik/management/commands/charger_plan_comptable.py`
(commande `--schema --jeu`, deux profils : `bar_resto` et `association`). On le
**complète sans renuméroter** : les numéros déjà présents (y compris ceux de la TVA)
restent ceux du chargeur. En revanche, des **correspondances changent** :
`SN` (Stripe carte), `SP` (SEPA) et `SR` (abonnement) pointent aujourd'hui vers le compte
CB (`51120001`) ou banque (`512000`) (~l.104-105, ~l.127-128) ; ils pointent désormais
vers **5171 Stripe**. `SF` (monnaie fédérée, aujourd'hui `None`) → 467. `QR` est
**retiré** de la table des moyens : aucun règlement ne porte ce code (un paiement QR/NFC
règle en `LE` / `SF`). Le profil `association` reçoit ce qui lui manque : 758, 658,
471, 467, 5171. Natures à couvrir
pour qu'un lieu neuf exporte sans rien saisir :

| Nature | Comptes |
|---|---|
| Ventes | prestations (billets), marchandises (bar), cotisations (adhésions), dons (prix libre, crowds) — par catégorie de caisse, et par type de produit (§3.3) |
| TVA | un compte par taux utilisé |
| Trésorerie | espèces, chèques, CB, **5171 Stripe** (fonds en attente de virement, pas 512 : Stripe vire plus tard, frais déduits), 512 banque (virements), 467 réseau fédéré (SF) |
| Tiers | **4191 avances clients** : recharges cashless et monnaie locale du lieu (D10) ; **471 compte d'attente** : moyen `UNKNOWN` (webhook legacy) |
| Écarts | **758** (catégorie « reçu en plus »), **658** (catégorie « reçu en moins ») (D26) |

Une recharge (article `hors_chiffre_affaires`) est créditée au compte donné par
`compte_pour_article` (4191) ; un écart, au 758 ou au 658 selon sa catégorie.
Consommation en monnaie locale du lieu → débit 4191.

## 4. Lisible pour un bénévole

- Menu « Ventes & comptabilité » : « Plan comptable », « Comptes des moyens de
  paiement », « Comptes des monnaies », sous les rapports.
- Liste des comptes **regroupée par nature**, une phrase d'aide par nature (« Ventes :
  ce que le lieu vend », « Trésorerie : où l'argent arrive »…).
- « Comptes des monnaies » : une ligne par monnaie **acceptée par le lieu** (lue dans
  fedow_core), compte à choisir ; une monnaie sans compte est signalée en orange
  (« l'export comptable sera refusé tant que ce compte manque »).
- Composant « Plan complet ? » en tête de page : ce qui manque pour exporter
  (produit vendu sans compte par sa catégorie ni par son type, moyen utilisé sans
  compte, monnaie sans compte, taux de TVA sans compte).
- Champ « prix d'achat » du produit : `help_text` « en centimes, par unité de vente
  (kg, litre, pièce) ; 0 = inconnu » (D21). Rien d'autre.

## 5. Tests

Fichier : `tests/pytest/test_plan_comptable_unique.py`.

| # | Test | Attendu |
|---|---|---|
| 1 | `test_compte_de_la_monnaie_prioritaire_sur_le_moyen` | LE avec mapping « Pêche » → son compte |
| 2 | `test_monnaie_du_lieu_sans_mapping_repli_sur_le_moyen` | TLF du lieu, pas de mapping → compte de `LE` |
| 2b | `test_monnaie_d_un_autre_lieu_sans_mapping_refus` | TLF d'un autre lieu (moyen `LE`) sans mapping → exception, pas de repli sur 4191 |
| 3 | `test_ni_monnaie_ni_moyen_erreur_explicite` | exception avec le nom du moyen |
| 4 | `test_moyens_hors_argent_sans_compte` | NA / LG / NM |
| 5 | `test_journal_du_point_de_vente` | PV « Bar » sans code → `BAR` (dérivé) ; code renseigné → utilisé tel quel |
| 6 | `test_journal_par_defaut_selon_origine` | les neuf `SaleOrigin` du tableau §3.2 ; une origine inconnue → erreur |
| 7 | `test_code_journal_collision_signalee` | deux PV de même préfixe sans code → « Plan complet ? » le signale, export refusé |
| 7c | `test_compte_article_par_categorie_de_caisse_puis_par_type` | produit bar avec catégorie → son compte ; billet sans catégorie → 706 ; adhésion → 756 ; recharge API v2 → 4191 ; contribution crowds → compte des dons ; numéro absent du plan → erreur |
| 7d | `test_compte_article_sans_categorie_ni_type_refus` | produit `NONE` sans catégorie → exception |
| 7e | `test_ecarts_758_et_658` | les deux catégories d'écart → 758 et 658 |
| 8 | `test_seed_lieu_neuf_plan_complet` | « Plan complet ? » ne signale rien pour les moyens et taux standard |
| 9 | `test_verification_signale_categorie_sans_compte` | |
| 10 | `test_csv_comptable_lit_le_plan_de_la_caisse` | |
| 11 | `test_modeles_comptabilite_en_doublon_retires` | `apps.get_model("comptabilite", "CompteComptable")` → `LookupError` |
| 12 | `test_seed_ne_renumerote_pas_les_comptes_existants` | profil `bar_resto` : numéros inchangés |

Vus rouges : tous (fonctions, modèles et champ absents ; 10 lit l'ancien plan) sauf 12
(non-régression).

Mutations : ordre monnaie / moyen inversé (1) ; repli silencieux au lieu de l'erreur
(3) ; repli sur le moyen pour toute monnaie (2b) ; journal toujours `WEB` (5, 6) ;
collision non signalée (7) ; type de produit ignoré (7c) ; un seul compte pour les
deux écarts (7e).

## 6. Tests existants à réécrire

| Fichier | Pourquoi | Quoi |
|---|---|---|
| `tests/pytest/test_comptabilite_models.py` | teste `comptabilite.CompteComptable` / `MappingMoyenDePaiement`, retirés | supprimé (raison notée dans le CHANGELOG) ; ses cas utiles passent dans `test_plan_comptable_unique.py` |
| `tests/pytest/test_comptabilite_csv_comptable.py` | `comptabilite/csv_comptable.py` lit désormais le plan de la caisse | les comptes créés par le test deviennent des `laboutik.CompteComptable` |
| `tests/pytest/test_profils_csv_comptable.py`, `tests/pytest/test_export_comptable.py`, `tests/pytest/test_hors_argent_offerts.py`, `tests/pytest/test_vente_en_points.py` | lisent `charger_plan_comptable` et les correspondances de moyens (`SN`, `SF`) | numéros inchangés ; correspondances `SN` → 5171 et `SF` → 467 mises à jour là où elles sont assertées |

Vérifier au démarrage : `rg -n "comptabilite.models import .*Compte|MappingMoyenDePaiement|charger_plan_comptable|51120001" tests/`.

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-E-plan-comptable.md` (migration
oui ; chaînes i18n : menus, aides par nature, messages de vérification, unités).
