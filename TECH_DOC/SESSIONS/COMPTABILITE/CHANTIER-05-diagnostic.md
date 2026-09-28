# Chantier 05 — Diagnostic (annexe)

> Relevé du 2026-09-28, en lecture seule (3 agents + second avis Fable).
> Hub : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md)
> Les numéros de ligne sont indicatifs (`~l.`) : le working tree porte le chantier 04
> non commité. Les revérifier au démarrage de chaque fiche.

Exemple fil rouge : **3 jus à 3,50 € payés 5,00 € en monnaie locale + 5,50 € CB.**
Aujourd'hui : deux `LigneArticle`, `amount` 350, `qty` 1.428571 (LE) et 1.571429 (CB).
`amount × qty` = 499,99985 et 550,00015. Valeurs justes : 500 et 550, total 1050,
HT 875, TVA 175 (20 %).

---

## 1. Qui fabrique des quantités fractionnaires

| Producteur | Fichier | `amount` | `qty` | Argent réel connu à la création |
|---|---|---|---|---|
| Caisse, cascade NFC (+ complément espèces/CB, 2ᵉ carte, legacy Fedow) | `laboutik/views.py` `_creer_lignes_articles_cascade` ~l.5559, `_calculer_qty_partielles` ~l.4507 | prix unitaire | part de la quantité (6 déc., la dernière ligne prend le reste) | oui : 3ᵉ élément de chaque tuple (`debit_sur_cet_asset` ~l.8188, `reste_article` ~l.8213, `couvert` legacy ~l.1429, part espèces/CB ~l.9546) — **jeté** |
| Tireuse | `controlvanne/billing.py` `facturer_tirage` ~l.332 | **total du tirage** | fraction de 1 | oui : `debits_par_asset` (~l.318) |
| Paiement QR / NFC en ligne | `BaseBillet/views.py` ~l.2005 (`process_with_nfc`), ~l.2231 (`valid_payment`) | total | fraction de 1 | oui : `transaction['amount']` |
| Avoirs et remboursements (recopient `-ligne.qty`) | `BaseBillet/views.py` ~l.4593, `BaseBillet/models.py` `_creer_avoir` ~l.2978, `booking/models.py` ~l.626, `Administration/admin_tenant.py` ~l.2101, `PaiementStripe/utils.py` ~l.78 | prix d'origine | `-qty` d'origine | hérite de la fraction |

Pas de fraction : prix libre et poids/mesure à la caisse (montant dans `amount`,
`qty = 1`, poids dans `weight_quantity`), billets, adhésions, booking, crowds.

Limite de l'arrondi actuel : l'écart d'une part vaut au plus
`(nombre de parts − 1) × prix × 5e-7`. Au-delà de 10 000 € de prix (ou de total pour
QR/tireuse), un écart d'un centime devient possible.

## 2. Qui lit l'argent d'une ligne (et se trompe)

| Lecteur | Fichier | Formule | Résultat sur l'exemple |
|---|---|---|---|
| `LigneArticle.total()` | `BaseBillet/models.py` ~l.3897 | quantize HALF_UP | 550 / 500 ✓ (corrigé récemment) |
| `Reservation.total_paid()` | `BaseBillet/models.py` ~l.2921 | Σ `int(amount×qty)` | 1049 ✗ — lu par le compte client, les e-mails, l'admin |
| `Paiement_stripe.total()` / `articles()` | `BaseBillet/models.py` ~l.3489, ~l.3509 | `int()` | 1049 ✗ |
| Fiche utilisateur admin | `Administration/admin_tenant.py` ~l.1176 | `int()` | 10,49 € ✗ |
| **Archive fiscale LNE** | `laboutik/archivage.py` ~l.178 | `total_tva = int(amount×qty) − total_ht` | TVA 174 au lieu de 175 ✗ |
| Compta en ligne | `comptabilite/services.py` ~l.93/124/177/253 | `int(Sum)` | 1049 ✗ ; HT + TVA = 1050 : incohérent |
| Rapports caisse | `laboutik/reports.py` ~l.37-51 `montant_ttc_centimes` | `Round(Sum)` par groupe | juste en pratique, ±1 c possible par groupe |
| HT par article vs par taux | `laboutik/reports.py` ~l.339-521 | `int(round())` à deux niveaux | Σ HT articles ≠ HT du taux (±1 c) |
| Écran « corriger le moyen » | `laboutik/views.py` ~l.10935 | `amount` seul | affiche 3,50 € au lieu de 5,50 € ✗ |

Autres défauts trouvés en lisant les lecteurs :

- **Adhésion payée avec plusieurs moyens** : la FK `membership` n'est posée que sur la
  1ʳᵉ part (`laboutik/views.py` ~l.8526-8534). 35 € = 20 LE + 15 CB → le Z, la
  synthèse et la facture comptent 20 €.
- **Avoirs admin invisibles du Z** : `calculer_remboursements` (`laboutik/reports.py`
  ~l.864) ne cherche que `amount < 0` ; un avoir admin a `qty < 0`.
- **Ticket Z** (`calculer_totaux_par_moyen` ~l.215) : les moyens hors des 5 seaux
  (UK, QR, SN…) sont ignorés dans les encaissements mais comptés dans les ventes ;
  LG compté comme de l'argent ; le fédéré est inclus dans le total sans ligne à lui.
- **Recharges** : comptées en ventes (article « Recharge » payé CASH, ~l.6686), puis
  la consommation cashless l'est aussi → double chiffre d'affaires (A1 du chantier 04).
- **Vider carte** (`fedow_core/services.py` ~l.643-676) : article « Refund » à 0 €,
  une ligne STRIPE_FED positive + une ligne CASH négative ; sans `total_ht`, sans HMAC.
- **Recharges caisse** : pas de `uuid_transaction` (`_executer_recharges` ~l.6695).
- **2ᵉ carte** : les lignes de la carte 2 portent `carte=carte1`.
- **Renouvellement d'abonnement Stripe** (`PaiementStripe/views.py` ~l.304) : met le
  total de la ligne Stripe dans `amount` **et** la quantité → double compte si qty > 1.
- Démo : `create_test_pos_data.py` ~l.1546 et `launch_payment.py` ~l.160 suivent
  l'ancienne convention (total dans `amount`).

## 3. Deux clôtures, deux plans comptables, deux FEC

| | Clôture « en ligne » | Clôture « caisse » (ticket Z LNE) |
|---|---|---|
| Modèle | `comptabilite.ClotureCaisse` (`comptabilite/models.py` ~l.26) | `laboutik.ClotureCaisse` (`laboutik/models.py` ~l.1226) — couvre déjà tout le lieu, le PV est informatif |
| Périmètre | tout **sauf** LABOUTIK (`comptabilite/services.py` ~l.59) → la TIREUSE est comptée **dans les deux** | LABOUTIK + TIREUSE (`laboutik/reports.py` ~l.84) |
| Numérotation / perpétuel | séquence globale ; perpétuel repris de la dernière J (`comptabilite/tasks.py` ~l.95-110) | séquence par niveau ; perpétuel cumulé dans `LaboutikConfiguration.total_perpetuel` (`laboutik/models.py` ~l.134) |
| Plan comptable | `comptabilite.CompteComptable` / `MappingMoyenDePaiement` (~l.149/196), utilisé seulement par `comptabilite/csv_comptable.py` | `laboutik.CompteComptable` (~l.1993 : numéro, libellé, nature, **taux de TVA**) / `MappingMoyenDePaiement` (~l.2117) ; `CategorieProduct.compte_comptable` (`BaseBillet/models.py` ~l.1154) pointe ici |
| FEC | `comptabilite/fec.py` : comptes **en dur**, crédite 706/756 en **TTC** + la TVA → **déséquilibre systématique** | `laboutik/ventilation.py` + `fec.py` : équilibre non garanti (HT par article vs TVA par taux, débits LG/SF sautés sans bruit, recharges comptées deux fois) ; clôtures M/A : écriture vide |

Le menu « Ventes & comptabilité » (`Administration/admin/dashboard.py` ~l.827-870)
ne montre que la clôture en ligne (« Rapports ») et « Entries » ; la clôture caisse
est dans une autre section (~l.477). Les entrées plan comptable sont en commentaire.

## 4. HMAC et empreintes

- `calculer_hmac` (`laboutik/integrity.py` ~l.28-70) : HMAC-SHA256 d'un JSON
  `[uuid, datetime, amount, total_ht, qty %.6f, vat %.2f, payment_method, status,
  sale_origin, weight_quantity, previous_hmac]`. Calculé **seulement** dans les deux
  fabriques de la caisse (~l.5529, ~l.5843). Tireuse, QR, vider carte, webhook Fedow :
  aucune empreinte.
- Une chaîne par `sale_origin`, triée `(datetime, pk)` avec `pk` UUID aléatoire.
  `verifier_chaine` saute les lignes sans empreinte et tolère les cassures couvertes
  par une `CorrectionPaiement` (mutation d'une ligne scellée).
- `calculer_hash_lignes` : caisse `uuid|amount|status` (sans `qty`, sans moyen) ;
  en ligne `pk:amount:qty:status`. Deux formats.
- Dev uniquement : le format peut être redéfini sans rien casser.

## 5. État de l'art (sources)

- **LNE v1.7, exigence 3** : par ligne, quantité, prix unitaire, **total HT de la
  ligne stocké comme donnée élémentaire**, taux de TVA ; pour la transaction, total
  TTC et **montants réglés par mode de paiement**. Exigence 4 : correction = opérations
  « plus » et « moins », jamais de modification. Clôture : total de la période + total
  perpétuel ; aucune obligation de ventiler par moyen ni par taux dans la clôture.
  https://www.eoxia.com/wp-content/uploads/2024/11/referentiel-certification-systemes-caisse.pdf
- **BOI-TVA-DECLA-30-10-30 § 50** : données d'origine = lignes + mode de règlement.
  https://bofip.impots.gouv.fr/bofip/10691-PGP.html/identifiant=BOI-TVA-DECLA-30-10-30-20250416
- **TVA** : due sur l'opération (par taux), jamais par règlement. France : TVA par
  ligne puis somme, ou par taux sur la base, admis si cohérent. EN 16931 BR-CO-17
  (facture électronique B2B) : par taux — non concerné par la caisse B2C.
- **Monnaie locale** : titre de paiement (L311-5 CMF) → règlement, pas une vente.
- **Petits cadeaux** (< 73 € TTC par bénéficiaire et par an) : pas de TVA (art. 257 CGI).
- **Modèle ERP / caisse** : Odoo `pos.order` / `pos.order.line` / `pos.payment` /
  `pos.payment.method` ; Dolibarr facture / lignes / paiements.
- **Money / allocate** (Fowler PoEAA, Dinero.js, plus grand reste) : montants en
  unités mineures entières, répartis sans perte. Stripe : entiers uniquement.
