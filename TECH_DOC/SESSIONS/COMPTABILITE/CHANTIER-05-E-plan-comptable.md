# Chantier 05-E — Un seul plan comptable, lisible, qui sépare tout

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28)
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D22, D23
> Effort : 1,5 j — Dépend de : rien (indépendante de A-D). **Migration : oui.**

## 1. Le besoin (mainteneur)

« On garde le plus complet et le plus agréable à lire, et on l'enrichit de ce qui
manque. Il faut arriver à dissocier les ventes en ligne, les points de vente, les
monnaies, la TVA. »

En comptabilité française, trois outils classiques suffisent :

| Pour séparer… | Outil | Exemple |
|---|---|---|
| la TVA | un compte par taux (existe) | 445711 (20 %), 445712 (10 %), 445713 (5,5 %) |
| les moyens **et les monnaies** | un compte de trésorerie par moyen, **et un par monnaie** | 530 espèces, 5112 CB, 4191-PECHE monnaie locale « Pêche » |
| les points de vente et le web | un **journal** par point de vente (colonne `JournalCode` du FEC) | `BAR`, `TIREUSE`, `WEB` |

## 2. Ce qu'on garde, ce qu'on retire

- **On garde les tables de la caisse** : `laboutik.CompteComptable` (`laboutik/models.py`
  ~l.1993 : numéro, libellé, nature, taux de TVA, actif) et
  `laboutik.MappingMoyenDePaiement` (~l.2117). Elles sont déjà reliées aux catégories
  (`CategorieProduct.compte_comptable`, `BaseBillet/models.py` ~l.1154) et utilisées
  par le FEC caisse. **On ne déplace pas les tables** (risque de migration sans gain) :
  elles sont **affichées** dans « Ventes & comptabilité ».
- **On retire** `comptabilite.CompteComptable` et `comptabilite.MappingMoyenDePaiement`
  (`comptabilite/models.py` ~l.149, ~l.196), leur admin (`comptabilite/admin.py`
  ~l.343, ~l.371) et leur seed. Leur seul lecteur (`comptabilite/csv_comptable.py`)
  lit désormais le plan de la caisse.

## 3. Ce qu'on ajoute

### 3.1 Un compte par monnaie (`laboutik.MappingMonnaie`, nouveau)

| Champ | Sens |
|---|---|
| `asset_uuid` | uuid de la monnaie (`fedow_core.Asset`, SHARED_APPS : pas de FK) |
| `nom_de_la_monnaie` | copie lisible (affichage) |
| `compte_de_tresorerie` | FK `CompteComptable` |

Règle unique de choix du compte d'un règlement :
`compte_pour_reglement(moyen, asset_uuid)` → le mapping de la **monnaie** s'il existe,
sinon le mapping du **moyen**, sinon **erreur explicite** (jamais de ligne sautée en
silence : D23).

Moyens sans écriture comptable (hors argent) : `FREE`, `LG` (offert), `NM` (points).
Ils ne demandent aucun compte.

### 3.2 Un journal par point de vente

- `PointDeVente.code_journal` : `CharField(max_length=10)`, défaut dérivé du nom
  (majuscules, sans accent, 10 caractères), modifiable.
- `journal_pour_vente(vente)` : le code du point de vente s'il y en a un, sinon selon
  l'origine :

| Origine | Journal par défaut |
|---|---|
| `LABOUTIK` sans point de vente | `CAISSE` |
| `TIREUSE` sans point de vente | `TIREUSE` |
| en ligne (`LESPASS`, API, `QRCODE_MA`, `NFC_MA`, crowds, booking) | `WEB` |
| `ADMIN` | `ADMIN` |

(à valider en relecture : le QR/NFC est-il « WEB » ou le journal du lieu ?)

### 3.3 Les comptes de base (seed, `charger_plan_comptable`)

Compléter le seed existant pour qu'un lieu neuf ait un plan **utilisable sans rien
saisir** :

| Nature | Comptes |
|---|---|
| Ventes | 706 prestations (billets), 707 marchandises (bar), 756 cotisations (adhésions), 7588 dons (prix libre / crowds) — par catégorie |
| TVA | 445711 / 445712 / 445713 / 445714 (20 / 10 / 5,5 / 2,1 %) |
| Trésorerie | 530 espèces, 5112 chèques, 5115 CB, 512 banque (Stripe), 467 réseau fédéré (SF) |
| Tiers | **4191 avances clients** : recharges cashless et monnaie locale du lieu (D10) |

Recharge (article `hors_chiffre_affaires`) → crédit **4191** (dette), pas un compte
de vente. Consommation en monnaie locale du lieu → débit 4191.

## 4. Lisible pour un bénévole

- Menu « Ventes & comptabilité » : « Plan comptable », « Comptes des moyens de
  paiement », « Comptes des monnaies », sous les rapports.
- Liste des comptes **regroupée par nature**, avec une phrase d'aide par nature
  (« Ventes : ce que le lieu vend », « Trésorerie : où l'argent arrive »…).
- Page « Comptes des monnaies » : une ligne par monnaie **acceptée par le lieu**
  (lue dans fedow_core), avec le compte à choisir ; une monnaie sans compte est
  signalée en orange (« l'export comptable sera refusé tant que ce compte manque »).
- Une vérification « Plan complet ? » (composant Unfold en tête de page) : liste ce qui
  manque pour exporter (catégorie sans compte, moyen utilisé sans compte, monnaie sans
  compte, taux de TVA sans compte).

## 5. Tests

Fichier : `tests/pytest/test_plan_comptable_unique.py`.

| # | Test | Attendu |
|---|---|---|
| 1 | `test_compte_de_la_monnaie_prioritaire_sur_le_moyen` | LE avec mapping monnaie « Pêche » → 4191-PECHE, pas le compte du moyen LE |
| 2 | `test_sans_mapping_monnaie_repli_sur_le_moyen` | → compte du moyen |
| 3 | `test_ni_monnaie_ni_moyen_erreur_explicite` | exception avec le nom du moyen |
| 4 | `test_moyens_hors_argent_sans_compte` | FREE / LG / NM → aucun compte demandé |
| 5 | `test_journal_du_point_de_vente` | PV « Bar » → `BAR` |
| 6 | `test_journal_par_defaut_selon_origine` | tableau §3.2 |
| 7 | `test_seed_lieu_neuf_plan_complet` | après `charger_plan_comptable`, la vérification « Plan complet ? » ne signale rien pour les moyens et taux standard |
| 8 | `test_verification_signale_categorie_sans_compte` | catégorie sans compte → signalée |
| 9 | `test_csv_comptable_lit_le_plan_de_la_caisse` | `comptabilite/csv_comptable.py` sort les numéros du plan caisse |
| 10 | `test_modeles_comptabilite_en_doublon_retires` | `apps.get_model("comptabilite", "CompteComptable")` lève `LookupError` |

Vus rouges : tous (fonctions et modèle absents ; 9 lit l'ancien plan).

Mutations : ordre monnaie / moyen inversé (1) ; repli silencieux au lieu de l'erreur
(3) ; journal toujours `WEB` (5, 6).

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-E-plan-comptable.md` (migration
oui ; chaînes i18n : libellés de menu, aides par nature, messages de vérification).
