# Chantier 05-F — Un moteur de rapport, une clôture, un FEC équilibré

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28) — relue Fable + Opus, corrigée
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D19 à D23, D26, D28, R2
> Effort : 3,5 j (3 sessions : §2, §3, §4, plus les tests existants du §7) — Dépend de :
> B, C, D (toutes les ventes ont leur `Vente`), E (plan comptable). **Migration : oui**
> (champs de clôture).

## 1. Le principe

Le rapport ne lit **que** des ventes encaissées (`Vente.statut = REGLEE`,
`datetime_encaissement` dans la période), leurs articles et leurs règlements, et ne
fait **que des sommes de champs entiers** (`Sum("total_ttc")`, `Sum("montant")`,
`Sum("cout_achat")`…). Plus de `amount × qty`, plus de `Round()`, plus de filtre par
`sale_origin` pour choisir un périmètre : **toutes les origines**.

Nouveau module : `comptabilite/rapport.py`, classe `RapportDesVentes(debut, fin)`, une
méthode explicite par section. Dès cette fiche, la clôture `comptabilite` et le menu
l'utilisent à la place de `comptabilite/services.py` `RapportComptableService` ; la
caisse bascule en fiche G. Les deux anciens modules restent dans le code (lus par
l'ancienne clôture caisse et par `tests/e2e/conftest.py` ~l.844) et sont retirés en H.

## 2. Session F-1 — le rapport (sections du Z)

Définitions (une seule fois, dans le module) :

- **Articles du chiffre d'affaires** : ventes `unite = EUR`, `hors_chiffre_affaires = False`,
  natures `VENTE` et `AVOIR`.
- **Articles servis** (pour la marge, D21) : les articles du chiffre d'affaires **et**
  les articles des ventes en points (`unite` ≠ EUR, `hors_chiffre_affaires = False`) ;
  jamais les recharges ni les écarts.
- **Argent** : règlements dont le moyen n'est ni `NA` (FREE), ni `LG`, ni `NM`. Parmi
  eux, **cashless** = règlement qui porte une monnaie (`asset` non vide : `LE`, `SF`) ;
  les autres sont l'argent au sens strict (espèces, CB, chèque, Stripe `SN`/`SP`/`SR`,
  virement, inconnu).
- Une section sur les recharges ou les écarts lit `hors_chiffre_affaires` et la
  catégorie de l'article, **jamais** `Vente.nature` (un panier bière + recharge est une
  vente `VENTE`).

**L'essentiel d'abord** (ce qu'un bénévole lit), le détail replié en annexe :

| # | Section | Contenu (entiers, sommes) |
|---|---|---|
| 1 | En-tête | lieu, période, niveau, n° de clôture, **plage de ventes [premier n°, dernier n°]**, nombre de ventes (dont ventes gratuites, numérotées elles aussi), total perpétuel |
| 2 | **Chiffre d'affaires** | TTC / HT / TVA ; **par taux** ; par catégorie ; **par origine** ; **par journal** (fiche E) |
| 3 | **Règlements** | natures `VENTE`, `AVOIR`, `CORRECTION` (le `VIDAGE_CARTE` est en 7) ; par moyen **et par monnaie**, en trois blocs : argent (espèces, CB, chèque, Stripe, virement, inconnu) ; cashless (monnaie locale par nom, fédérée) ; hors argent (offert, jetons, points par monnaie). Les règlements d'une vente `CORRECTION` sont comptés dans la **J où la correction est faite**. Une correction n'est possible que tant que la vente d'origine n'est couverte par aucune J (garde, fiche G) : les deux sont donc presque toujours dans la même J |
| 4 | Caisse espèces | fond, espèces reçues, sorties (`SortieCaisse`), espèces rendues, solde théorique |
| 5 | Réconciliation | une phrase : « Argent reçu = ventes payées en argent + recharges − remboursements − cartes vidées ± écarts d'encaissement », avec les chiffres |
| 6 | Offerts | par source (OFFRIR, jetons) : quantités, valeur catalogue, coût d'achat — **articles du chiffre d'affaires seulement** (la recharge cadeau n'y est pas : pas de double compte avec les jetons consommés) |
| *Annexe* | | |
| 7 | Avoirs, recharges, écarts, corrections | quatre sous-listes, même code : **avoirs** (nombre, total, par moyen ; dont **retours consigne**, D11 ; dont **remboursements Stripe à faire à la main : n / X €** = règlements Stripe négatifs sans `reference_externe`, D27) ; **recharges et cartes** (recharges encaissées par moyen ; cadeau émis ; cartes vidées, espèces rendues) ; **écarts d'encaissement** (nombre, total, D26 — en rouge s'il y en a) ; **corrections** (moyen avant → après, opérateur) |
| 8 | Points | par monnaie |
| 9 | **Marge brute** (D21) | CA HT − `Sum("cout_achat")` des **articles servis** (vendus, offerts, points ; retours de consigne en négatif) ; nombre d'articles au coût inconnu (prix d'achat 0) : « marge incomplète : 12 articles sans prix d'achat » |
| 10 | Détail | billets (par événement, tarif), adhésions, ventes par produit (qté, TTC, HT, offert, coût) — **ce qui est imprimé sur le Z aujourd'hui**, réécrit sur les champs entiers. « Habitus cartes » et « opérateurs » restent au rapport X, hors du Z stocké |
| 11 | Intégrité | `verifier_chaine_ventes` sur la plage : « OK » ou les anomalies |

Le rapport X (temps réel) = ce même calcul, non stocké, plus « habitus cartes » et
« opérateurs » (sections actuelles de `laboutik/reports.py`, réécrites sur les entiers).

## 3. Session F-2 — la clôture unique (`comptabilite.ClotureCaisse`)

### 3.1 La journée (D28)

- **Clôture J** = `[fin de la J précédente, moment de la clôture]` : bouton de la caisse
  en fin de service (branché en fiche G), et **filet automatique à l'heure de fermeture du
  lieu + 2 h, heure locale** (`Configuration.fuseau_horaire`, `BaseBillet/models.py`
  ~l.544). L'heure de fermeture n'existe pas encore : un seul champ ajouté,
  `Configuration.heure_de_fermeture` (`TimeField`, défaut **02:00** → Z automatique à
  **4 h**), réglable dans l'admin (migration dans cette fiche). **Condition du filet** :
  en heure locale, il est **au moins** l'heure de fermeture + 2 h, **et** il y a des
  ventes encaissées depuis la dernière J. Jamais une égalité d'heure : elle raterait
  l'heure sautée au changement d'heure, et la condition « ≥ et ventes depuis la dernière
  J » est idempotente (rejouée une heure plus tard, elle ne crée rien). Une seule J à la
  fois (verrou du lieu, le même que les ventes).
- **Planification** (`TiBillet/celery.py` ~l.108-128, à modifier dans cette fiche) :
  aujourd'hui `cron_cloture_quotidienne` tourne à 6:00 UTC pour tous les lieux
  (`CELERY_TIMEZONE` = variable d'environnement `TIME_ZONE`, `TiBillet/settings.py`
  ~l.656). Elle devient une tâche **horaire** (`crontab(minute=0)`) qui ne clôture que
  les lieux où la condition ci-dessus est vraie. Les tâches H / M / A gardent leur heure ;
  leurs bornes calendaires sont calculées en heure locale du lieu.
- **H, M, A** : **calendaires** (semaine du lundi au dimanche, mois, année), calculées
  **directement sur les ventes** de la période. Une J de soirée à cheval sur deux mois
  est découpée par la date d'encaissement de chaque vente : la M reste juste.
- Idempotence : aujourd'hui fondée sur `(niveau, début, fin)` avec une J calendaire
  (bornes : `comptabilite/tasks.py` ~l.50-51 ; contrainte `unique_cloture_periode` :
  `comptabilite/models.py` ~l.139). Nouvelle règle : J = « pas de nouvelle J sans vente
  depuis la précédente » ; H/M/A = unique sur `(niveau, début, fin)` (inchangé).

### 3.2 Les champs

Champs existants gardés (`total_general` = CA TTC, `total_ht`, `total_tva`,
`numero_sequentiel` **unique**, séquence globale tous niveaux, `rapport_json`).
Ajoutés / changés :

| Champ | Sens |
|---|---|
| `point_de_vente` | informatif (depuis quel poste la J a été lancée), nullable |
| `numero_premiere_vente`, `numero_derniere_vente` | plage couverte |
| `total_argent_recu` | bloc « argent » des règlements |
| `total_perpetuel` | cumul du CA TTC de toutes les J depuis la mise en service, jamais remis à zéro (définition actuelle, `comptabilite/tasks.py` ~l.95-110) |
| `nombre_ventes_perpetuel` | cumul du nombre de ventes |
| `hmac_hash`, `previous_hmac` | la clôture est chaînée : HMAC (JSON canonique : totaux, plage, empreinte de la dernière vente couverte, `previous_hmac`) |
| `rapport_json` | **toutes** les sections du §2, figées |
| `hash_lignes` | **retiré** (remplacé par la plage + la chaîne des ventes) |

### 3.3 Transition F → G

La clôture de la caisse (`laboutik.ClotureCaisse`, son bouton, `laboutik/tasks.py`)
tourne encore jusqu'à G : entre F et G, une vente de caisse apparaît dans les deux
clôtures (dev, accepté). Menu : « Rapport ventes en ligne » devient **« Rapport des
ventes »** ; « Rapport ventes caisse » devient **« Ancien rapport caisse »** (retiré en H).

## 4. Session F-3 — FEC et CSV comptables, équilibrés par construction

Une seule fonction `ventiler_cloture(cloture_j)` (`comptabilite/ventilation.py`, remplace
`laboutik/ventilation.py` et la logique de `comptabilite/fec.py`) produit **une écriture
par journal** et par clôture **J** :

| Côté | Ligne | Montant |
|---|---|---|
| Débit | un compte par (moyen, monnaie) des règlements d'**argent et cashless** (`compte_pour_reglement`) | Σ règlements |
| Crédit | articles du CA : `compte_pour_article` (catégorie de caisse, sinon type de produit, fiche E §3.3) | Σ `total_ht` |
| Crédit | TVA : un compte par taux | Σ `total_tva` |
| Crédit | articles hors CA : `compte_pour_article` (recharges → 4191, écart reçu en plus → 758, reçu en moins → 658) | Σ `total_ttc` (TVA 0) |

- **Équilibre garanti** : pour chaque vente en euros, Σ règlements hors offert = Σ nets
  (égalité de la fiche A) = Σ HT + Σ TVA (CA) + Σ nets hors CA. Les ventes en points
  (`unite` ≠ EUR) n'ont d'écriture d'aucun côté. Chaque vente va entièrement dans un
  seul journal (`journal_pour`) : chaque écriture de journal est équilibrée. La fonction **vérifie** débits = crédits et
  **refuse** l'export sinon (message lisible), au lieu du simple avertissement actuel.
- Montant négatif (avoir, espèces rendues, écart négatif) → écrit **du côté opposé**,
  en positif (convention FEC).
- Offerts, jetons, points : **aucune écriture** (pas d'argent).
- Compte manquant → refus explicite (fiche E).
- **Le FEC n'est produit que par les J.** Une période (mois, année) s'exporte en
  concaténant les écritures des J qu'elle contient. Les clôtures H / M / A sont des
  **rapports**, sans écriture propre (plus d'écriture vide).
- **J à cheval sur minuit ou sur deux mois** **(décidé par le mainteneur le
  2026-09-29)** : l'écriture FEC d'une J est **datée du jour de début de service**
  (date locale de la première vente de la J) ; elle va dans le mois de cette date. Le
  rapport M, lui, compte chaque vente à sa date d'encaissement (calendaire, D28). Aux
  bords de mois, le FEC du mois et le rapport M peuvent donc différer des ventes faites
  après minuit : l'écart est écrit dans le rapport M (« dont ventes de la J du … comptées
  au FEC du mois précédent ») ; **le FEC fait foi par J**.
- `ventiler_cloture` remplace `laboutik/ventilation.py` et `comptabilite/fec.py` pour la
  clôture unique ; les anciens fichiers restent pour l'ancienne clôture caisse jusqu'à
  G, et sont retirés en H.
- Profils CSV comptables (Sage, EBP, Paheko… : `laboutik/csv_comptable.py`,
  `laboutik/profils_csv.py`, `comptabilite/csv_comptable.py`, `comptabilite/profils_csv.py`) :
  un seul jeu survit (le plus complet, à comparer au démarrage), il lit **cette**
  ventilation ; l'autre est retiré en H.

## 5. Test de comparaison avec les anciens rapports

`tests/pytest/test_rapport_unique_comparaison.py` (**schéma dédié**) : **trois
scénarios** que les anciens moteurs calculaient juste — espèces, CB, NFC mono-monnaie
— avec, pour chacun, les mêmes totaux TTC / HT / TVA et les mêmes règlements dans
l'ancien moteur caisse et dans `RapportDesVentes`. Pas de liste d'écarts : les valeurs
exactes des tests du §6 tiennent ce rôle pour tout ce que les anciens moteurs
calculaient faux (troncatures, recharges dans le CA, jetons comptés en argent, tireuse
comptée deux fois, adhésion multi-moyens, avoirs admin invisibles).

## 6. Tests

Fichiers : `tests/pytest/test_rapport_unique.py`, `tests/pytest/test_cloture_unique.py`,
`tests/pytest/test_fec_equilibre.py` — **schéma dédié**.

| # | Test | Attendu |
|---|---|---|
| 1 | `test_ca_trois_jus_nfc_et_cb_1050_875_175` | l'exemple fil rouge |
| 2 | `test_ca_par_taux_egal_somme_des_lignes` | exactement |
| 3 | `test_jetons_hors_ca_et_hors_argent_mais_dans_offerts` | bière 300 jetons + 200 CB → CA 200, argent 200, offerts 300 |
| 4 | `test_recharge_cadeau_puis_jetons_offert_compte_une_fois` | recharge cadeau 1000, bière 300 en jetons → offerts 300 |
| 5 | `test_recharge_encaissee_hors_ca_puis_consommation_dans_ca` | recharge 2000 CB, bière 500 LE → CA 500, argent 2000 |
| 6 | `test_panier_biere_et_recharge_section_recharges` | la recharge est vue alors que la vente est `VENTE` |
| 7 | `test_consigne_dans_ca_retour_en_avoir` | vente 100, retour −100 → CA 0, « retours consigne » 1 |
| 7b | `test_remboursements_stripe_a_faire_a_la_main_dans_le_z` | avoir admin d'une ligne Stripe (D27, sans `reference_externe`) → section 7 « à faire à la main : 1 / 35,00 € » ; un avoir Stripe avec référence n'y est pas |
| 8 | `test_vider_carte_especes_rendues` | espèces rendues en section 7 ; **rien** en section 3 (règlements) |
| 9 | `test_ecart_d_encaissement_section_et_reconciliation` | |
| 10 | `test_ventilation_par_origine_et_par_journal` | caisse BAR + web → deux lignes |
| 11 | `test_marge_brute_somme_des_couts_et_compte_inconnus` | valeurs + compteur |
| 12 | `test_correction_comptee_dans_la_j_de_la_correction` | vente et correction dans la même J : −CA +CB dans cette J ; vente d'origine inchangée |
| 13 | `test_vente_en_attente_hors_rapport` | |
| 14 | `test_cloture_j_fin_de_service_plage_et_perpetuel` | plage, perpétuel = précédent + CA |
| 15 | `test_filet_4h_cree_la_j_seulement_s_il_y_a_des_ventes` | |
| 15c | `test_filet_suit_l_heure_de_fermeture_plus_deux_heures` | fermeture 23:00 → Z à 1 h ; défaut 02:00 → Z à 4 h |
| 15b | `test_filet_4h_heure_locale_du_lieu` | lieu en `Europe/Paris` et lieu en `America/Martinique` : la tâche horaire ne clôture que celui où il est **au moins** 4 h avec des ventes depuis la dernière J ; rejouée une heure plus tard, elle ne crée pas de seconde J |
| 16 | `test_mois_calendaire_egal_ventes_du_mois` | une J à cheval sur deux mois : chaque vente dans son mois |
| 17 | `test_cloture_hebdomadaire_calendaire_non_vide` | |
| 18 | `test_cloture_chainee_et_alteration_detectee` | modifier `rapport_json` → vérification KO |
| 19 | `test_fec_equilibre_sur_le_scenario_complet` | débits = crédits |
| 20 | `test_fec_egal_au_z` | pour chaque compte de règlement, **solde net** (débits − crédits) = Σ règlements du Z pour ce moyen et cette monnaie ; pour chaque compte de vente / TVA / hors CA, solde net (crédits − débits) = total du Z correspondant. Le scénario contient un avoir et un vidage de carte (montants négatifs) |
| 21 | `test_fec_avoir_ecrit_du_cote_oppose_en_positif` | aucun montant négatif |
| 22 | `test_fec_refuse_si_compte_manquant` | |
| 23 | `test_fec_un_journal_par_point_de_vente` | |
| 24 | `test_fec_aucune_ecriture_pour_offerts_et_points` | |
| 25 | `test_fec_mois_concatene_les_journees` | |
| 25b | `test_fec_j_a_cheval_sur_deux_mois_datee_du_debut_de_service` | J du 31 à 22 h au 1ᵉʳ à 2 h → écriture datée du 31 |
| 25c | `test_marge_brute_compte_les_points` | vente en points avec prix d'achat → coût compté dans la marge |
| 26 | `test_aucun_amount_fois_qty_dans_le_rapport` | garde sur `comptabilite/rapport.py` et `ventilation.py` |

Vus rouges : tous (module absent). Et, **sur l'ancien code**, un test dédié appelle
`laboutik/fec.py` puis `comptabilite/fec.py` sur le scénario : déséquilibre observé
(sortie notée dans le CHANGELOG).

Mutations : lire `LigneArticle` hors vente (13) ; inclure LG dans l'argent (3) ; compter
la recharge cadeau dans les offerts (4) ; filtrer les recharges par `nature` (6) ;
marge recalculée par `qty × prix` (11) ; marge limitée aux articles du CA (25c) ; M = Σ
des J (16) ; supprimer le refus d'export (19, 22) ; écrire un avoir en négatif (21) ;
filet à 4 h UTC (15b) ; filet sur l'égalité d'heure au lieu de « ≥ et ventes depuis la
dernière J » (15b rejouée) ; remboursements Stripe sans référence comptés comme faits
(7b) ; vidage de carte compté en section 3 (8) ; écriture datée de la clôture (25b).

## 7. Tests existants à réécrire

La J change de sens (glissante), `hash_lignes` est retiré, la clôture `comptabilite`
lit `RapportDesVentes`. Fichiers concernés (vérifiés au 2026-09-28 par
`rg -l "comptabilite\.(services|tasks|fec)|hash_lignes|_bornes_pour_niveau|cron_cloture" tests/`) :

| Fichier | Quoi |
|---|---|
| `tests/pytest/test_comptabilite_service.py` | teste l'ancien moteur en ligne : gardé tel quel jusqu'à H (le module reste), les cas utiles sont repris dans `test_rapport_unique.py` |
| `tests/pytest/test_comptabilite_celery.py` | J calendaire → J glissante et filet de 4 h local ; H/M/A calendaires |
| `tests/pytest/test_comptabilite_verify.py` | `verify_clotures` : `hash_lignes` retiré → plage de ventes + chaîne des clôtures |
| `tests/pytest/test_comptabilite_admin.py`, `tests/pytest/test_comptabilite_exports.py`, `tests/pytest/test_comptabilite_csv_comptable.py` | champs de clôture ajoutés / retirés, `rapport_json` aux sections du §2 |
| `tests/pytest/test_demo_data_ventes.py` | lit `comptabilite.services` : à relire, adapter si l'assertion porte sur la clôture |
| `tests/e2e/conftest.py` (~l.785-920) | compare les deux anciens moteurs : inchangé jusqu'à H (les modules restent) |

Chaque réécriture est listée dans le CHANGELOG avec sa raison.

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-F-rapport-unique.md`.
