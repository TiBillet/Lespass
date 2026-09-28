# Chantier 04-D — Hors argent : OFFRIR en mode gérant, recharges cadeau, section « Offerts »

> **Statut** : ✅ LIVRÉ (non commité) le 2026-09-28 — voir CHANGELOG
> Tronc commun : [`CHANTIER-04-melanges-argent.md`](CHANTIER-04-melanges-argent.md)
> Décisions : D6 à D11, D15, D28
> Effort estimé : 3 j (2 sessions, §5)

---

## 1. La situation, simplement

Une ligne de caisse **« offerte »** porte `payment_method = FREE` (code `"NA"`).
Aujourd'hui, à la caisse, elle vient de :

| Origine | `amount` | Existe en pratique ? |
|---|---|---|
| **Recharge cadeau** (produit `RECHARGE_CADEAU`) : le lieu crédite de la monnaie cadeau sur une carte (`_executer_recharges` ~l.6293-6297 ; chemins NFC ~l.7911, 8360, 8947, 9501) | valeur créditée (ex. 1000) | **oui** (2 lignes en dev, 10 € chacune) |
| **Panier gratuit** (billet à 0 €, `moyen_paiement=gift`, `laboutik/views.py` ~l.6800-6830) | 0 | oui |
| **Bouton OFFRIR** d'un panier payant | prix | **non** (voir ci-dessous) |
| **Commande de table**, POST `gift` (`payer_commande`, chemin non-NFC ~l.11168-11174) | prix | **oui, par un trou** : le moyen posté est transmis sans aucune garde |

**Le bouton OFFRIR existe mais ne s'affiche jamais, et le serveur le refuse** :

```python
# laboutik/views.py ~l.6468 — vue moyens_paiement
est_mode_gerant = False                      # ← en dur : la tuile OFFRIR n'apparait jamais

# laboutik/views.py ~l.6800 — _executer_paiement
if moyen_paiement_code == "gift":
    panier_est_gratuit = total_centimes == 0 and len(articles_panier) > 0
    if not panier_est_gratuit:               # ← un panier payant est refuse
        ... « Ce panier n'est pas gratuit. » (400)
```

Le reste est prêt : la tuile (`_tuiles_paiement.html:60`, `{% if mode_gerant %}`,
`data-testid="paiement-btn-offrir"`), `CartePrimaire.edit_mode`
(`laboutik/models.py` ~l.931, chargée par `_charger_carte_primaire` ~l.996), la carte
primaire postée au paiement (`tag_id_cm`, ~l.6621), et `"gift" → PaymentMethod.FREE`
(~l.4143).

**Référence LaBoutik v1** : une carte primaire en mode gérant fait apparaître
« offrir » au choix du moyen de paiement (`LaBoutik/webview/validators.py` ~l.299).
La vente est enregistrée **avec son prix** ; le ticket Z v1 sépare les quantités
offertes (et leur coût d'achat) du chiffre d'affaires
(`LaBoutik/administration/ticketZ.py` ~l.185-215).

### Ce que les rapports font d'une ligne FREE avec montant

Base : `self.lignes` (`laboutik/reports.py` ~l.180) = toutes les lignes valides
LABOUTIK + TIREUSE de la période, **sans filtre de moyen de paiement**.

| Calcul (`laboutik/reports.py`) | Ligne FREE comptée comme de l'argent ? |
|---|---|
| `calculer_totaux_par_moyen` (l.193) → `total_general`, `total_perpetuel` | non ✅ |
| `calculer_detail_ventes` (l.317) | **oui** — `methodes_cadeau` (l.343-345) = `[LOCAL_GIFT]` (+ `EXTERIEUR_GIFT` s'il existe) : FREE tombe dans « vendus » (l.379-381) |
| `calculer_tva` (l.461) | **oui** — aucun filtre |
| `calculer_recharges` (l.547) | **oui** — `total_recharges` (l.611) additionne l'entrée FREE |
| `calculer_adhesions` (l.620), `calculer_billets` (l.817) | **oui** (montants) |
| `calculer_habitus` (l.706) | **oui** — lignes avec `carte` (recharges cadeau NFC) |
| `calculer_ventilation_par_pv` (l.943) | **oui** |
| `calculer_solde_caisse`, `calculer_synthese_operations` | non (zones vérifiées, on n'y touche pas) |

**Conséquence comptable** : `laboutik/ventilation.py` `ventiler_cloture()` (l.83)
prend le **débit** dans `totaux_par_moyen` (sans FREE) et le **crédit** dans
`detail_ventes` + `tva` (avec FREE). L'écriture FEC n'est pas équilibrée, du montant
offert ; un avertissement est journalisé (~l.226-243), sans bloquer. Les exports
PDF / CSV / Excel du Z héritent du défaut.

**La TVA d'une ligne FREE** : `LigneArticle.save()` (`BaseBillet/models.py`
~l.3868-3879) remplace une TVA **nulle ou absente** par celle du produit, à la
création. Passer `vat=0` depuis la vue ne sert donc à rien.

**Correction de moyen de paiement** (`corriger_moyen_paiement`, `laboutik/views.py`
~l.10414-10490 ; formulaire ~l.10335 ; `laboutik/serializers.py` ~l.335) : la cible
est déjà limitée à espèces / CB / chèque, mais la source n'est refusée que pour
LE et LG (~l.10478). **Une recharge cadeau (FREE) peut aujourd'hui être « corrigée »
en espèces** : 10 € apparaissent dans le tiroir du Z sans avoir été encaissés.

## 2. Le correctif

### 2.1 Un seul endroit décide de ce qui est « de l'argent »

```python
# laboutik/reports.py

# Moyens de paiement qui ne sont PAS de l'argent : un article offert (la valeur
# offerte reste sur la ligne) et une vente en points ou en temps (fiche 04-E).
# Ces lignes restent dans le perimetre de la cloture (hash, chainage, compteurs)
# mais n'entrent dans AUCUN calcul d'argent : total, TVA, CA, FEC.
# / Payment methods that are NOT money. They stay in the closure scope
#   but never in any money computation.
MOYENS_HORS_ARGENT = [PaymentMethod.FREE]   # + PaymentMethod.NON_MONETAIRE (fiche E)

class RapportComptableService:
    def __init__(self, point_de_vente, datetime_debut, datetime_fin):
        ...
        self.lignes = LigneArticle.objects.filter(...)          # inchange
        # Les lignes qui representent de l'argent. Tout calcul de montant part d'ici.
        # / Lines that represent money. Every amount computation starts here.
        self.lignes_argent = self.lignes.exclude(payment_method__in=MOYENS_HORS_ARGENT)
```

| Méthode | Changement |
|---|---|
| `calculer_detail_ventes` | lit `lignes_argent` ; un article seulement offert n'y apparaît plus (il est dans « Offerts ») |
| `calculer_tva`, `calculer_habitus`, `calculer_ventilation_par_pv` | lisent `lignes_argent` |
| `calculer_recharges` | **total encaissé** sur `lignes_argent` ; recharges FREE sur une ligne « Cadeau émis (hors argent) », par monnaie (D9) |
| `calculer_billets`, `calculer_adhesions` | `"payment_method"` ajouté au `.values()`, accumulation en Python : **nombre** sur toutes les lignes, **montants** hors `MOYENS_HORS_ARGENT` (D10) |
| `calculer_totaux_par_moyen`, `calculer_solde_caisse`, `calculer_synthese_operations`, `calculer_hash_lignes` | inchangés |

La colonne `qty_offerts` / `ttc_offerts` du détail des ventes compte les articles
payés en **monnaie cadeau** (LG). Ses **libellés** d'affichage deviennent « Payé en
cadeau » (D8) ; les clés JSON ne changent pas (clôtures existantes, exports).

### 2.2 La section « Offerts »

```python
def calculer_offerts(self):
    """
    Articles offerts (bouton OFFRIR) : quantite, valeur offerte, cout d'achat.
    Ce n'est pas de l'argent encaisse : jamais additionne a un total.
    Les recharges cadeau n'y sont pas : elles sont dans calculer_recharges.
    / Gifted items: quantity, gifted value, purchase cost. Never money.
    """
```

- Lignes : `self.lignes.filter(payment_method=FREE)` **sans** les produits de
  recharge (`methode_caisse` RC).
- Par produit : `qty`, `valeur` (`montant_ttc_centimes()`), `cout_achat`
  (`qty × prix_achat`, comme v1). Totaux : `qty_totale`, `valeur_totale`.
- Clé `"offerts"` dans `generer_rapport_complet()` (14ᵉ clé). Le ticket X
  (`recap_en_cours`, ~l.3520-3530) appelle les méthodes une par une : y ajouter
  `calculer_offerts()` explicitement.

### 2.3 TVA 0 sur les lignes hors argent (D11)

Dans `LigneArticle._compute_default_vat()` (`BaseBillet/models.py` ~l.3849), en
premier :

```python
# Une ligne offerte ou payee en points/temps n'est pas une vente en argent :
# pas de TVA. Sans cette regle, save() pose la TVA du produit sur une ligne
# creee sans TVA, et l'archive fiscale exporterait une TVA inventee.
# Limite : la regle joue a la CREATION seulement, et pas si l'appelant passe
# lui-meme une TVA non nulle.
# / A gifted or points/time line is not a money sale: no VAT (on creation).
if self.payment_method in (PaymentMethod.FREE, PaymentMethod.NON_MONETAIRE):
    return Decimal("0.00")
```

Portée : les lignes **créées** en FREE sans TVA explicite. Les créations de la
caisse ne passent pas `vat` (~l.5030-5045, 5339-5357) : elles sont couvertes. Les
lignes passées en FREE **après** création (`booking/booking_engine.py:743`,
`BaseBillet/validators.py:310`, `services_commande.py:534`) gardent leur TVA.
Autres créateurs FREE touchés (hors caisse, `amount` souvent 0) :
`BaseBillet/validators.py:1126-1140`, `services_commande.py:497`,
`api_v2/views.py:993`, `api_v2/serializers.py:1462`, `admin_tenant.py:3103`. Pour les
recharges offertes de l'API (74 lignes avec montant en dev), la TVA tombe à 0 :
même sens que le constat A5 (hors chantier). Aucun test n'asserte la TVA d'une
ligne FREE (vérifié). À noter dans le CHANGELOG.
(`NON_MONETAIRE` est ajouté par la fiche E.)

### 2.4 OFFRIR en mode gérant (D6)

1. **Affichage** — vue `moyens_paiement` (~l.6468) : `est_mode_gerant` =
   `carte_primaire.edit_mode` de la carte `tag_id_cm` postée (même chargement que
   `_valider_carte_primaire_pour_pv`, ~l.1504). Sans carte primaire : `False`.
2. **Adhésions et billets** — la popup de paiement « client identifié »
   (`_rendre_popup_paiement_client_identifie`, ~l.4779) force `mode_gerant: False` :
   elle reçoit elle aussi `tag_id_cm` et calcule le mode gérant de la même façon.
3. **Montant affiché** — la tuile appelle `confirmer?method=gift` **sans**
   `&total=` : l'écran de confirmation affiche « 0,00 € ». Ajouter
   `&total={{ total|unlocalize }}` comme les autres tuiles.
4. **Garde serveur** — `_executer_paiement` (~l.6800) : `gift` est accepté si le
   panier est gratuit, **ou** si la carte primaire postée est en `edit_mode`
   **lu en base**. Refusé dans tous les cas : panier avec **retour de consigne**
   (sinon une ligne offerte négative), panier avec **recharge euros (RE)** (offrir
   créerait de la monnaie locale remboursable : `_payer_par_carte_ou_cheque` appelle
   `_executer_recharges(..., "gift")`, ~l.6960-6968), panier en points (fiche E).
5. **Commandes de table** — `payer_commande` (~l.11168) : liste blanche des moyens
   non-NFC (`espece`, `carte_bancaire`, `CH`). Ferme le trou existant du POST `gift`.
6. **Enregistrement** — inchangé : `"gift" → FREE`, `amount` = prix unitaire, `qty`
   = quantité, TVA 0 (§2.3). Adhésions et billets offerts : créés par les fonctions
   existantes (`_creer_adhesions_depuis_panier`, `_creer_billets_depuis_panier`).

Limite connue (à documenter, pas à bloquer) : le mode gérant repose sur le secret
du tag de la carte primaire, comme tout l'accès caisse. La carte de démo
(`create_test_pos_data.py` ~l.1231, `A49E8E2A`) est en `edit_mode=True` : la tuile
OFFRIR apparaîtra dans les parcours de démo et E2E (aucun test ne compte les tuiles).

### 2.5 Correction de moyen de paiement (D15)

- `corriger_moyen_paiement` (~l.10478) : la garde 1 refuse aussi
  `MOYENS_HORS_ARGENT` en source :

```python
moyens_non_corrigeables = (
    PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT, *MOYENS_HORS_ARGENT,
)
```

- `Administration/admin/laboutik.py` ~l.1683-1706 (`MappingMoyenDePaiementAdmin`,
  mapping moyen → compte de trésorerie du FEC) : NA et NM retirés des choix.

### 2.6 Affichage

| Fichier | Ajout |
|---|---|
| `laboutik/templates/laboutik/partial/hx_cloture_rapport.html` | bloc « Offerts » (`data-testid="cloture-offerts"`) ; ligne « Cadeau émis (hors argent) » ; libellé « Payé en cadeau » |
| `laboutik/templates/laboutik/partial/hx_recap_en_cours.html` (ticket X) | idem (`data-testid="recap-offerts"`) |
| `Administration/templates/admin/cloture/rapport_temps_reel.html` (~l.202), `rapport_before.html` (~l.128), export `Administration/admin/laboutik.py` (~l.990) | idem |
| `laboutik/printing/formatters.py` `formatter_ticket_x` / `formatter_ticket_cloture` | « Offerts : N articles, valeur X » |
| `laboutik/pdf.py`, `csv_export.py`, `excel_export.py` | section « Offerts » |

Libellés en `{% translate %}`, texte source français.

## 3. Tests

Schéma de test dédié (D28) pour tout ce qui lit un rapport. Mise en place à copier
de `tests/pytest/test_paiement_complementaire.py` (setUp cartes et assets) et de
`test_ventes_remontent_au_ticket_z.py` (`_encaisser`, ~l.209-230, POST réel
`/laboutik/paiement/payer/`, à compléter avec `tag_id_cm`). Il faut une
`CartePrimaire` liée à une `CarteCashless` et au point de vente. Pour le FEC : une
`ClotureCaisse` avec `rapport_json` et les `laboutik.models.MappingMoyenDePaiement`,
catégories et comptes de TVA du schéma (modèle : `tests/pytest/test_profils_csv_comptable.py`
~l.155-180).

| # | Scénario | Assertions |
|---|---|---|
| D1 | `moyens_paiement`, carte primaire `edit_mode=True` | tuile `paiement-btn-offrir` rendue, avec `total=` dans son URL (rouge) |
| D2 | idem, `edit_mode=False` | pas de tuile (vert : non-régression) |
| D3 | POST `gift`, panier 2 × 500 cts TVA 20 %, carte gérant | 1 ligne FREE, `amount == 500`, `qty == 2`, `vat == 0` (rouge) |
| D4 | POST `gift`, panier payant, carte **non** gérant | refus 400, aucune ligne (vert : non-régression) |
| D5 | POST `gift`, carte gérant, panier avec recharge RE | refus, aucune ligne, aucun crédit (vert aujourd'hui, **doit rester vert** après D3) |
| D5b | POST `gift`, carte gérant, panier de retour de consigne | refus (vert aujourd'hui, doit rester vert) |
| D5c | popup « client identifié » (adhésion), carte gérant | tuile OFFRIR rendue ; POST `gift` → adhésion créée, ligne FREE à son prix (rouge) |
| D5d | `payer_commande` POST `gift` sur une commande de table | refus (rouge : trou existant) |
| D6 | article A offert 2 × 500 (D3) + article B vendu espèces 500 | `totaux_par_moyen["total"] == 500` ; `tva` : 500 TTC seulement ; `detail_ventes` ne contient que B (rouge) |
| D7 | D6 | `rapport["offerts"]` : A, qty 2, valeur 1000 (rouge) |
| D8 | FEC de D6 | `ventiler_cloture()` équilibrée, aucun avertissement « déséquilibre » (rouge) |
| D9 | recharge cadeau NFC 1000 + recharge euros 2000 | `recharges["total"] == 2000` ; « cadeau émis » == 1000 (rouge) |
| D10 | carte : recharge cadeau NFC 1000 + achat 500 | `habitus` : panier moyen et recharge médiane sans les 1000 (rouge) |
| D11 | **billet payant offert** (FREE, 1000) + billet payant vendu 1000 | `billets` : nombre 2, montant 1000 (rouge) |
| D12 | ventilation par PV après D6 | CA du PV == 500 (rouge) |
| D13 | ticket X (`hx_recap_en_cours`) après D6 | `data-testid="recap-offerts"` avec la valeur (rouge) |
| D14 | `corriger_moyen_paiement` sur la ligne FREE d'une recharge cadeau | refus, ligne inchangée (rouge) |
| D15 | admin du mapping FEC | NA absent des choix (rouge) |

### Mutations à jouer

| Mutation | Test qui doit tomber |
|---|---|
| `est_mode_gerant = False` rétabli | D1 |
| garde `gift` : `edit_mode` lu dans le POST au lieu de la base | D4 |
| garde « pas de recharge RE offerte » retirée | D5 |
| garde « pas de consigne offerte » retirée | D5b |
| liste blanche de `payer_commande` retirée | D5d |
| `self.lignes_argent = self.lignes` | D6, D8, D9, D10, D12 |
| règle TVA 0 retirée de `_compute_default_vat` | D3 |
| `calculer_offerts` filtre sur `LOCAL_GIFT` | D7 |
| `calculer_billets` compte le nombre hors FREE | D11 |
| `MOYENS_HORS_ARGENT` retiré de la garde de correction | D14 |

## 4. Fichiers touchés

| Fichier | Changement |
|---|---|
| `laboutik/reports.py` | `MOYENS_HORS_ARGENT`, `lignes_argent`, 7 méthodes, `calculer_offerts` |
| `BaseBillet/models.py` | `_compute_default_vat` : TVA 0 pour FREE |
| `laboutik/views.py` | mode gérant (`moyens_paiement`, popup client identifié), garde `gift`, `recap_en_cours`, `payer_commande`, `corriger_moyen_paiement` |
| `laboutik/templates/laboutik/partial/_tuiles_paiement.html` | `&total=` sur la tuile OFFRIR |
| `Administration/admin/laboutik.py` | choix du mapping FEC ; export Z |
| templates Z / X (caisse et admin), `formatters.py`, `pdf.py`, `csv_export.py`, `excel_export.py` | sections « Offerts », « Cadeau émis », « Payé en cadeau » |
| nouveau `tests/pytest/test_hors_argent_offerts.py` | D1-D15 |

Pas de migration. Nouvelles chaînes traduisibles : à signaler au mainteneur.

## 5. Découpage en sessions

| Session | Contenu |
|---|---|
| D-1 | `MOYENS_HORS_ARGENT`, `lignes_argent`, 7 méthodes, `calculer_offerts`, TVA 0, correction de paiement, affichages Z / X / admin / exports (D6-D15 hors OFFRIR : tests avec lignes FREE de recharge cadeau et billet offert créés via `_creer_lignes_articles`) |
| D-2 | OFFRIR : mode gérant, popup client identifié, gardes consigne / RE, `payer_commande`, tuile `&total=` (D1-D5d) |
