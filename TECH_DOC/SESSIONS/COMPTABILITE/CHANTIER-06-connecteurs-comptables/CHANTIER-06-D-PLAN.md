# Chantier 06-D — Plan de code : les ventes de TiBillet dans Dolibarr

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**RÈGLE GIT ABSOLUE : aucune opération git en écriture (ni add, ni commit, ni stash, ni checkout, ni restore, ni reset). Le mainteneur commite lui-même, sans `Co-Authored-By`. Chaque tâche se termine par un message de commit PROPOSÉ, rien de plus.**

**Goal :** chaque nuit, en mode « articles et ventes », Dolibarr recopie les ventes de chaque clôture J de TiBillet en factures payées, avoirs, virements internes et paiements divers, avec un résultat compte par compte égal au FEC.

**Architecture :** TiBillet fait **tout le calcul** : une fonction Python `vente_a_facturer()` découpe chaque vente en lignes de facture, paiements, virements internes et paiements divers, avec les comptes de TiBillet. Elle réutilise les règles du FEC, sans les recopier. Une action `sales` de l'API des clôtures la publie, page par page. Le module Dolibarr ne décide rien : il recopie, vente par vente, une transaction par vente, et s'arrête à la première vente refusée.

**Tech Stack :** Django 4 / DRF (`viewsets.ViewSet`), django-tenants, pytest (`FastTenantTestCase`) ; PHP 8, Dolibarr 24 (classes `Facture`, `Paiement`, `Account`, `PaymentVarious`, `Societe`), script d'essai `scripts/essai.php`.

**Spec :** [`CHANTIER-06-D-ventes.md`](CHANTIER-06-D-ventes.md) (décisions D1-D24, questions Q1-Q11 tranchées). Contexte : [`CHANTIER-06-C-catalogue.md`](CHANTIER-06-C-catalogue.md), [`CHANTIER-06-A-api-comptable.md`](CHANTIER-06-A-api-comptable.md).

## Global Constraints

- Code **FALC** : noms verbeux en français, commentaires bilingues FR puis EN (une ligne), au présent, qui décrivent le code et ne racontent pas la session. Django : skill `/djc`, `GUIDELINES.md`, `api_v2/GUIDELINES.md`. PHP : conventions Dolibarr (tabulations, `$this->db`, `$langs->transnoentities`).
- `get_apikey_valid` (`ApiBillet/permissions.py`) **n'est pas modifiée** (B1 de 06-C).
- Montants en **centimes entiers** dans l'API (`"amountUnit": "cent"`), comme `entries`.
- L'API est rendue sous `translation.override("fr")`.
- Ventes lues : `statut=REGLEE`, `unite="EUR"`, `numero` dans la plage de la J. Les ventes CORRECTION sont écartées : leurs règlements sont ajoutés à ceux de la vente corrigée.
- Acheteur : **`Vente.client` seul** (D4), publié par **son e-mail seul** et son uuid (Q4). Tiers Dolibarr retrouvé **par e-mail** ; s'il y en a plusieurs, le plus ancien (Q3).
- Date des factures, paiements, virements et paiements divers : **`accountingDate` de la J, à midi** (D23).
- **Pas de temps réel** : l'import est lancé par Dolibarr, une fois par jour (tâche planifiée du module, heure réglable, **06:00 par défaut** : après la clôture J automatique de TiBillet, fermeture + 2 h), ou à la main par le bouton de la page. Il ne lit que des J clôturées. TiBillet n'envoie jamais rien.
- Une facture par vente (Q1), en copiant TakePOS **sans** `module_source='takepos'`.
- Recharges et vidages : **virements internes** (Q11). Recharge offerte, jetons repris et écarts : **paiements divers** (Q2, Q5).
- Droit de la clé pour `/closures/<uuid>/sales/` : `comptabilite` **et** `sale` (Q7).
- Le module règle lui-même ce qui manque dans Dolibarr et le dit sur sa page (Q10). Il n'active que les taux de TVA utilisés.
- Pas de `ruff format` sur un fichier existant. Pas de `makemessages` ni de `compilemessages`. `poetry`, `pytest` et `ruff` **seulement dans le conteneur** (`docker exec lespass_django …`).
- **Ne jamais lancer la suite pytest et `essai.php` en même temps** : la suite écrit des ventes dans le lieu `lespass`.
- Chaque test est vu **rouge** avant le code, puis une **mutation** volontaire doit le refaire échouer (fichier restauré et contrôlé par `sha256sum`).

## Review Focus

1. **Vente mêlant une bière et une recharge, payée en un seul règlement CB** : une facture égale au prix de la bière, payée en CB, plus un virement interne de la banque de la monnaie vers la banque CB du montant de la recharge. Rien d'autre. → test de la tâche 2.
2. **Avoir dont la vente liée n'a jamais été importée** (J d'avant le mode ventes) : un avoir seul, sans `fk_facture_source`, jamais une erreur. → essai de la tâche 9.
3. **Vente sans aucun montant** (jus offert par le bouton OFFRIR) : rien n'est publié, rien n'est écrit. → test de la tâche 4.
4. **Tiers dont l'e-mail a changé de casse** (`Alice@Exemple.fr` puis `alice@exemple.fr`) : le même tiers. → essai de la tâche 8.
5. **Coupure au milieu d'une J** (limite de ventes atteinte) : la nuit suivante reprend à la vente suivante, sans doublon ni trou de numéro de facture. → essai de la tâche 9.

---

## Les fichiers

**Lespass**

| Fichier | Rôle |
|---|---|
| `laboutik/plan_comptable.py` (modifié) | `est_une_recharge(produit)` : le test de recharge du FEC, rendu public |
| `comptabilite/ventilation.py` (modifié) | `_ecrire_la_recharge_offerte` appelle `est_une_recharge` |
| `comptabilite/ventes_a_facturer.py` (neuf) | `vente_a_facturer()`, `ventes_a_facturer_de_la_cloture()`, `RepartitionImpossible` |
| `api_v2/permissions.py` (modifié) | `CleAvecLeDroitDesVentes` |
| `api_v2/views.py` (modifié) | action `ClosureViewSet.sales` |
| `api_v2/serializers.py` (modifié) | `VenteAFacturerSerializer` |
| `api_v2/openapi-schema.yaml`, `api_v2/GUIDELINES.md` (modifiés) | la route |
| `tests/pytest/fabriques_vente.py` (modifié) | paramètre `client=None` de `fabriquer_vente_encaissee` |
| `tests/pytest/test_ventes_a_facturer.py` (neuf) | la découpe d'une vente |
| `tests/pytest/test_fec_equilibre.py` (modifié) | un test : ventes à facturer = FEC, compte par compte |
| `tests/pytest/test_api_v2_ventes_comptables.py` (neuf) | la route |
| `CHANGELOG/2026-10-xx-ventes-comptables.md` (neuf) | |

**Module `tibillet-dolibarr`**

| Fichier | Rôle |
|---|---|
| `sql/llx_tibillet_vente_importee.sql`, `.key.sql` (neufs) | les ventes importées |
| `sql/llx_tibillet_cloture_importee.sql` (modifié) + `sql/llx_tibillet_cloture_importee-mode.sql` (neuf) | la colonne `mode` |
| `class/reglages.class.php` (neuf) | `ReglagesTiBillet` : banques, codes de paiement, taux et comptes de TVA, tiers de passage |
| `class/ventes.class.php` (neuf) | `VentesTiBillet` : l'import des ventes |
| `class/importtibillet.class.php` (modifié) | `passageDeLaNuit` : catalogue puis ventes ; `noterLaCloture` écrit le mode |
| `admin/setup.php`, `langs/*/tibillet.lang` (modifiés) | page : réglages faits, banques, dernier passage, bouton |
| `scripts/essai.php` (modifié) | essais 22 et suivants |
| `README.md` (modifié) | |

---

## Partie A — Lespass

### Task 1 : `est_une_recharge`, sortie du FEC sans copie

**Files :**
- Modify : `laboutik/plan_comptable.py` (près de `METHODES_CAISSE_DES_RECHARGES`, l.686)
- Modify : `comptabilite/ventilation.py:247-273` (`_ecrire_la_recharge_offerte`)
- Test : `tests/pytest/test_fec_equilibre.py` (existant, inchangé)

**Interfaces :**
- Produces : `est_une_recharge(produit) -> bool` dans `laboutik.plan_comptable`.

- [ ] **Step 1 : écrire la fonction**

```python
def est_une_recharge(produit):
    """
    Vrai pour un produit de recharge cashless : par son mode de caisse (recharge en
    euros, recharge cadeau) ou par son type (recharge, recharge fédérée).
    / True for a cashless top-up product, by POS method or by product type.

    LOCALISATION : laboutik/plan_comptable.py

    LU PAR : comptabilite/ventilation.py (la recharge offerte du FEC) et
    comptabilite/ventes_a_facturer.py (la recharge devient un virement interne).
    """
    if produit.methode_caisse in METHODES_CAISSE_DES_RECHARGES:
        return True
    if produit.categorie_article in TYPES_DE_PRODUIT_DES_RECHARGES:
        return True
    return False
```

- [ ] **Step 2 : `_ecrire_la_recharge_offerte` l'appelle**

Remplacer les lignes :

```python
    produit = ligne.pricesold.productsold.product
    est_une_recharge = (
        produit.methode_caisse in METHODES_CAISSE_DES_RECHARGES
        or produit.categorie_article in TYPES_DE_PRODUIT_DES_RECHARGES
    )
    if not est_une_recharge:
        return
```

par :

```python
    produit = ligne.pricesold.productsold.product
    if not est_une_recharge(produit):
        return
```

Puis ajuster les imports de `ventilation.py`. Retirer `METHODES_CAISSE_DES_RECHARGES` et `TYPES_DE_PRODUIT_DES_RECHARGES` seulement s'ils ne servent plus (`rg -n "METHODES_CAISSE_DES_RECHARGES|TYPES_DE_PRODUIT_DES_RECHARGES" comptabilite/ventilation.py`).

- [ ] **Step 3 : les tests du FEC passent**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_fec_equilibre.py -q`
Expected : tous verts. C'est un déplacement : aucun test neuf.

- [ ] **Step 4 : mutation**

Faire rendre `False` à `est_une_recharge`, relancer : `test_fec_equilibre_sur_le_scenario_complet` et `test_fec_jetons_cadeau_d8_bis` échouent. Restaurer et contrôler le `sha256sum`.

- [ ] **Step 5 : message de commit proposé** — `refactor(compta): est_une_recharge() partagée par le FEC`

---

### Task 2 : `vente_a_facturer()` — la découpe d'une vente

**Files :**
- Create : `comptabilite/ventes_a_facturer.py`
- Modify : `tests/pytest/fabriques_vente.py:110` (paramètre `client=None`, transmis à `ouvrir_vente`)
- Test : `tests/pytest/test_ventes_a_facturer.py` (neuf, schéma `test_ventes_a_facturer`)

**Interfaces :**
- Consumes : `est_une_recharge` (Task 1) ; `compte_pour_article`, `compte_pour_reglement(moyen, asset_uuid)`, `compte_de_tva_pour_taux(taux)`, `compte_des_ventes_reglees_en_jetons(comptes)`, `compte_des_cadeaux_a_la_clientele(comptes)`, `comptes_du_plan_par_defaut_du_lieu()` (tous dans `laboutik.plan_comptable`).
- Produces :
  - `class RepartitionImpossible(Exception)` ;
  - `vente_a_facturer(vente, comptes_du_plan_par_defaut, compte_par_moyen_et_monnaie, compte_de_tva_par_taux) -> dict | None`. Rend `None` pour une vente sans montant. Sinon, un dict :

```python
{
    "vente": Vente,
    "nature": "sale" | "refund" | "card_emptying",
    "client": TibilletUser | None,
    "lignes_de_la_facture": [
        {"tarif": Price | None, "libelle": str, "quantite": Decimal,
         "prix_unitaire_ttc": int, "total_ttc": int, "total_ht": int,
         "total_tva": int, "taux_de_tva": Decimal,
         "compte": CompteComptable, "compte_de_tva": CompteComptable | None},
    ],
    "paiements_de_la_facture": [
        {"compte": CompteComptable, "moyen": str | None, "montant": int},
    ],
    "virements": [
        {"depuis": CompteComptable, "moyen_depuis": str | None,
         "vers": CompteComptable, "moyen_vers": str | None,
         "montant": int, "libelle": str},  # montant > 0
    ],
    "paiements_divers": [
        {"compte_de_tresorerie": CompteComptable, "moyen": str | None,
         "montant": int, "contrepartie": CompteComptable, "libelle": str},
        # montant > 0 : l'argent entre dans la banque ; < 0 : il sort
    ],
}
```

**La règle de découpe (FALC), à recopier en tête du module :**
1. **Lignes de la facture** : les articles du chiffre d'affaires (`hors_chiffre_affaires=False`) dont `total_ttc != 0`.
   - La part payée en jetons (`part_en_jetons`) devient une ligne à part : sans tarif, « Part payée en jetons — <libellé> », compte 707900, TVA 0.
   - Le reste devient une ligne au tarif vendu : TTC = `total_ttc - part_en_jetons`, HT = `total_ht - part_en_jetons`, TVA = `total_tva`.
   - Une ligne de **retour de consigne** (mode de caisse `RETOUR_CONSIGNE`) porte le **premier tarif en euros du gobelet** (`consigne_remboursee`, `asset` vide, ordre `order` puis `uuid`), Q6.
2. **Soldes de trésorerie** : les règlements de la vente **et** de ses ventes CORRECTION, additionnés par compte (`compte_pour_reglement`, gardé par (moyen, monnaie)). L'offert (`NA`) et les points (`NM`) n'ont pas de compte : on les ignore. Chaque compte garde le moyen de son premier règlement.
3. **Recharges** (article hors CA, `est_une_recharge`) : le solde du compte de la monnaie (`compte_pour_article`) **baisse** du TTC. Leur part offerte devient un **paiement divers** sur ce compte (montant négatif), avec la contrepartie 623400 et le libellé « Recharge offerte ».
4. **Autres articles hors CA** (écart, jetons repris, virement reçu, fidélité) dont `total_ttc != 0` : un **besoin** (montant = TTC, contrepartie = `compte_pour_article`).
5. **Répartition** : chaque besoin (les besoins hors CA d'abord, la facture ensuite) prend sur les soldes **de même signe**, dans l'ordre. Ce qui reste est pris sur le premier solde, quel qu'en soit le signe. Un besoin hors CA donne des paiements divers, la facture donne ses paiements.
6. **Virements** : ce qui reste des soldes fait zéro au total. Un solde négatif envoie vers un solde positif, dans l'ordre, jusqu'à ce que tout soit à zéro. Si le total ne fait pas zéro, on lève `RepartitionImpossible` avec le numéro de vente et l'écart.

Cette répartition garde, compte par compte, la même somme que le FEC : le test de la tâche 3 le vérifie.

- [ ] **Step 1 : `client` dans la fabrique**

Dans `fabriquer_vente_encaissee`, ajouter le paramètre `client=None` après `carte=None`, le transmettre à `ouvrir_vente(..., client=client, ...)`, et l'ajouter au docstring (`:param client: le TibilletUser de la vente, ou None`).

- [ ] **Step 2 : écrire les tests rouges**

`tests/pytest/test_ventes_a_facturer.py` : même en-tête que `tests/pytest/test_api_v2_comptabilite.py` (bootstrap django, `FastTenantTestCase`, schéma `test_ventes_a_facturer`, domaine `test-ventes-a-facturer.tibillet.localhost`, `setUp` qui pose le tenant et `LaboutikConfiguration.get_solo().save()`). Les outils et les tests :

```python
    def _decouper(self, vente):
        """La vente découpée, comptes lus ici. / The sale, split."""
        return vente_a_facturer(vente, comptes_du_plan_par_defaut_du_lieu(), {}, {})

    def _numeros(self, elements, cle):
        """[(numéro du compte, montant)] / [(account number, amount)]"""
        return [(element[cle].numero_de_compte, element["montant"]) for element in elements]

    def test_biere_en_especes_une_ligne_un_paiement(self):
        biere = creer_tarif_vendu(nom="Biere", prix_en_euros="5.00", methode_caisse=Product.VENTE)
        self._relier_a_la_categorie_707(biere)
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            articles=[{"pricesold": biere, "quantite": Decimal("1"), "prix_unitaire": 500, "taux_tva": Decimal("20")}],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 500}],
        )
        decoupe = self._decouper(vente)
        assert decoupe["nature"] == "sale"
        assert decoupe["client"] is None
        ligne = decoupe["lignes_de_la_facture"][0]
        assert (ligne["tarif"], ligne["total_ttc"], ligne["total_ht"], ligne["total_tva"]) == (biere.price, 500, 417, 83)
        assert ligne["compte"].numero_de_compte == "707000"
        assert ligne["compte_de_tva"].numero_de_compte == "445711"
        assert self._numeros(decoupe["paiements_de_la_facture"], "compte") == [("530000", 500)]
        assert decoupe["virements"] == [] and decoupe["paiements_divers"] == []

    def test_biere_et_recharge_payees_en_cb_facture_plus_virement(self):
        # 5 € de bière + 10 € de recharge en monnaie locale, un seul règlement CB de 15 €.
        ...
        assert self._numeros(decoupe["paiements_de_la_facture"], "compte") == [("512100", 500)]
        virement = decoupe["virements"][0]
        assert (virement["depuis"].numero_de_compte, virement["vers"].numero_de_compte, virement["montant"]) == (
            compte_de_la_monnaie_locale, "512100", 1000)

    def test_recharge_seule_sans_ligne_de_facture(self): ...   # lignes == [], un virement
    def test_biere_payee_en_monnaie_locale(self): ...          # paiement de la facture au compte de la monnaie
    def test_recharge_offerte_paiement_divers_623400(self): ...# montant négatif, contrepartie 623400
    def test_vidage_jetons_repris_et_argent_rendu(self): ...    # paiement divers +Y (623400) ; virement caisse -> monnaie
    def test_jetons_cadeau_ligne_707900_a_part(self): ...       # deux lignes : jetons 707900 TVA 0 + reste
    def test_ecart_stripe_en_moins_paiement_divers_658(self): ...  # facture 1000, paiement Stripe 1000, divers -2 / 658
    def test_correction_especes_vers_cb_un_seul_paiement_cb(self): ...
    def test_avoir_nature_refund_montants_negatifs(self): ...
    def test_retour_de_consigne_au_premier_tarif_du_gobelet(self): ...
    def test_client_de_la_vente_seul_jamais_la_carte(self):
        # client=None, carte liée à un user APRÈS la vente → client None.
        ...
    def test_vente_sans_montant_rend_none(self): ...            # jus offert par OFFRIR
    def test_repartition_impossible_nomme_la_vente(self): ...   # vente en euros avec un règlement NM (points) : lève
```

Les corps marqués `...` suivent le modèle du premier test. Les scénarios sont ceux, déjà écrits, de `tests/pytest/test_fec_equilibre.py` : `_recharge_offerte` l.523, `_biere_payee_en_jetons` l.549, `_vidage_avec_jetons_repris` l.582, `_jus_offert_par_le_bouton_offrir` l.613, `_gobelet_consigne_vendu_puis_rendu` l.692, `_billet_vendu_en_ligne_par_stripe` l.441, `_corriger_les_especes_en_cb` l.507, `_avoir_par_le_bouton_de_l_admin` l.488. On les recopie dans des outils du nouveau fichier, avec les montants vérifiés à la main dans le commentaire, comme l.973-997 de ce fichier.

- [ ] **Step 3 : voir rouge**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_ventes_a_facturer.py -q`
Expected : `ImportError: cannot import name 'vente_a_facturer'`.

- [ ] **Step 4 : écrire `comptabilite/ventes_a_facturer.py`**

```python
"""
Une vente TiBillet telle qu'un logiciel de facturation la recopie (fiche 06-D).
/ A TiBillet sale as an invoicing software copies it.

LOCALISATION : comptabilite/ventes_a_facturer.py

<la règle de découpe, points 1 à 6, recopiée ici>

LU PAR : api_v2/views.py (ClosureViewSet.sales).
"""

from decimal import Decimal

from BaseBillet.models import PaymentMethod, Product
from BaseBillet.models_vente import Vente
from laboutik.plan_comptable import (
    compte_de_tva_pour_taux,
    compte_des_cadeaux_a_la_clientele,
    compte_des_ventes_reglees_en_jetons,
    compte_pour_article,
    compte_pour_reglement,
    est_une_recharge,
)

NATURE_PUBLIEE = {
    Vente.Nature.VENTE: "sale",
    Vente.Nature.AVOIR: "refund",
    Vente.Nature.VIDAGE_CARTE: "card_emptying",
}


class RepartitionImpossible(Exception):
    """Les règlements d'une vente ne couvrent pas ses articles. / Payments do not match items."""


def _libelle_du_tarif(tarif):
    return f"{tarif.product.name} — {tarif.name}"


def _premier_tarif_en_euros(produit):
    """Le premier tarif sans monnaie TiBillet (donc en euros), ordre du catalogue."""
    return produit.prices.filter(asset__isnull=True).order_by("order", "uuid").first()


def _lignes_de_la_facture(vente, comptes_du_plan_par_defaut, compte_de_tva_par_taux):
    lignes = []
    for article in vente.articles.all():
        if article.hors_chiffre_affaires or article.total_ttc == 0:
            continue
        produit = article.pricesold.productsold.product
        tarif = article.pricesold.price
        if produit.methode_caisse == Product.RETOUR_CONSIGNE:
            tarif = _premier_tarif_en_euros(produit.consigne_remboursee)
        libelle = _libelle_du_tarif(article.pricesold.price)

        part_en_jetons = article.part_en_jetons
        if part_en_jetons != 0:
            lignes.append({
                "tarif": None,
                "libelle": f"Part payée en jetons — {libelle}",
                "quantite": Decimal("1"),
                "prix_unitaire_ttc": part_en_jetons,
                "total_ttc": part_en_jetons,
                "total_ht": part_en_jetons,
                "total_tva": 0,
                "taux_de_tva": Decimal("0"),
                "compte": compte_des_ventes_reglees_en_jetons(comptes_du_plan_par_defaut),
                "compte_de_tva": None,
            })

        total_ttc_du_reste = article.total_ttc - part_en_jetons
        if total_ttc_du_reste == 0:
            continue
        compte_de_tva = None
        if article.vat != 0:
            if article.vat not in compte_de_tva_par_taux:
                compte_de_tva_par_taux[article.vat] = compte_de_tva_pour_taux(article.vat)
            compte_de_tva = compte_de_tva_par_taux[article.vat]
        lignes.append({
            "tarif": tarif,
            "libelle": libelle,
            "quantite": article.qty,
            "prix_unitaire_ttc": article.amount,
            "total_ttc": total_ttc_du_reste,
            "total_ht": article.total_ht - part_en_jetons,
            "total_tva": article.total_tva,
            "taux_de_tva": article.vat,
            "compte": compte_pour_article(article, comptes_du_plan_par_defaut),
            "compte_de_tva": compte_de_tva,
        })
    return lignes


def _reglements_nets(vente):
    """Les règlements de la vente et de ses CORRECTION (même règle que
    laboutik/affichage_des_ventes.py:reglements_nets_de_la_vente, sans addition)."""
    reglements = list(vente.reglements.all())
    for vente_derivee in vente.ventes_derivees.all():
        if vente_derivee.nature == Vente.Nature.CORRECTION:
            reglements.extend(vente_derivee.reglements.all())
    return reglements


def _ajouter_au_solde(soldes, compte, moyen, montant):
    numero = compte.numero_de_compte
    if numero not in soldes:
        soldes[numero] = {"compte": compte, "moyen": moyen, "solde": 0}
    soldes[numero]["solde"] += montant


def _prendre_sur_les_soldes(soldes, montant_du_besoin):
    """
    [(solde, montant pris)] : d'abord sur les soldes de même signe, dans l'ordre ; le
    reste sur le premier solde. / Takes from same-sign balances, the rest from the first.
    """
    prises = []
    reste = montant_du_besoin
    for solde in soldes.values():
        if reste == 0:
            break
        meme_signe = (solde["solde"] > 0 and reste > 0) or (solde["solde"] < 0 and reste < 0)
        if not meme_signe:
            continue
        if reste > 0:
            pris = min(reste, solde["solde"])
        else:
            pris = max(reste, solde["solde"])
        solde["solde"] -= pris
        reste -= pris
        prises.append((solde, pris))
    if reste != 0:
        premier_solde = next(iter(soldes.values()))
        premier_solde["solde"] -= reste
        prises.append((premier_solde, reste))
    return prises


def vente_a_facturer(vente, comptes_du_plan_par_defaut, compte_par_moyen_et_monnaie, compte_de_tva_par_taux):
    """<docstring FALC : la règle, les paramètres (dicts partagés comme ventiler_cloture), le retour, RepartitionImpossible>"""
    lignes = _lignes_de_la_facture(vente, comptes_du_plan_par_defaut, compte_de_tva_par_taux)

    soldes = {}
    for reglement in _reglements_nets(vente):
        cle = (reglement.moyen, reglement.asset)
        if cle not in compte_par_moyen_et_monnaie:
            compte_par_moyen_et_monnaie[cle] = compte_pour_reglement(reglement.moyen, reglement.asset)
        compte = compte_par_moyen_et_monnaie[cle]
        if compte is None:
            continue
        _ajouter_au_solde(soldes, compte, reglement.moyen, reglement.montant)

    paiements_divers = []
    besoins_hors_facture = []
    for article in vente.articles.all():
        if not article.hors_chiffre_affaires:
            continue
        produit = article.pricesold.productsold.product
        compte_de_l_article = compte_pour_article(article, comptes_du_plan_par_defaut)
        if est_une_recharge(produit):
            if article.total_ttc != 0:
                _ajouter_au_solde(soldes, compte_de_l_article, None, -article.total_ttc)
            if article.part_offerte != 0:
                paiements_divers.append({
                    "compte_de_tresorerie": compte_de_l_article,
                    "moyen": None,
                    "montant": -article.part_offerte,
                    "contrepartie": compte_des_cadeaux_a_la_clientele(comptes_du_plan_par_defaut),
                    "libelle": "Recharge offerte",
                })
            continue
        if article.total_ttc != 0:
            besoins_hors_facture.append({
                "montant": article.total_ttc,
                "contrepartie": compte_de_l_article,
                "libelle": _libelle_du_tarif(article.pricesold.price),
            })

    total_de_la_facture = sum(ligne["total_ttc"] for ligne in lignes)
    rien_a_ecrire = (
        not lignes and not besoins_hors_facture and not paiements_divers
        and all(solde["solde"] == 0 for solde in soldes.values())
    )
    if rien_a_ecrire:
        return None

    total_des_soldes = sum(solde["solde"] for solde in soldes.values())
    total_des_besoins = total_de_la_facture + sum(besoin["montant"] for besoin in besoins_hors_facture)
    if total_des_soldes != total_des_besoins or (total_des_besoins != 0 and not soldes):
        raise RepartitionImpossible(
            f"Vente n° {vente.numero} : les règlements ({total_des_soldes} centimes) ne "
            f"couvrent pas les articles ({total_des_besoins} centimes)."
        )

    for besoin in besoins_hors_facture:
        for solde, pris in _prendre_sur_les_soldes(soldes, besoin["montant"]):
            paiements_divers.append({
                "compte_de_tresorerie": solde["compte"], "moyen": solde["moyen"],
                "montant": pris, "contrepartie": besoin["contrepartie"], "libelle": besoin["libelle"],
            })

    paiements_de_la_facture = []
    if total_de_la_facture != 0:
        for solde, pris in _prendre_sur_les_soldes(soldes, total_de_la_facture):
            paiements_de_la_facture.append({"compte": solde["compte"], "moyen": solde["moyen"], "montant": pris})

    virements = []
    soldes_negatifs = [solde for solde in soldes.values() if solde["solde"] < 0]
    soldes_positifs = [solde for solde in soldes.values() if solde["solde"] > 0]
    for depuis in soldes_negatifs:
        for vers in soldes_positifs:
            if depuis["solde"] == 0:
                break
            montant = min(-depuis["solde"], vers["solde"])
            if montant == 0:
                continue
            virements.append({
                "depuis": depuis["compte"], "moyen_depuis": depuis["moyen"],
                "vers": vers["compte"], "moyen_vers": vers["moyen"],
                "montant": montant, "libelle": "Vidage de carte" if vente.nature == Vente.Nature.VIDAGE_CARTE else "Recharge cashless",
            })
            depuis["solde"] += montant
            vers["solde"] -= montant

    return {
        "vente": vente,
        "nature": NATURE_PUBLIEE[vente.nature],
        "client": vente.client,
        "lignes_de_la_facture": lignes,
        "paiements_de_la_facture": paiements_de_la_facture,
        "virements": virements,
        "paiements_divers": paiements_divers,
    }
```

Le code ci-dessus est la logique attendue. À l'écriture, on la met au format FALC du projet : boucles simples, commentaires bilingues, `sum(...)` remplacé par une boucle si le relecteur le demande. Vérifier aussi les noms de constantes : `Product.RETOUR_CONSIGNE` (`rg -n "RETOUR_CONSIGNE" BaseBillet/models.py`) et `Vente.Nature.*`.

- [ ] **Step 5 : voir vert**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_ventes_a_facturer.py -q`
Expected : tous verts.

- [ ] **Step 6 : mutations** (une à la fois ; restaurer et contrôler le `sha256sum` après chacune)
  - (a) Ne plus ajouter les règlements des CORRECTION : le test de correction échoue.
  - (b) `vente.carte.user` en repli quand `client` est vide : le test « jamais la carte » échoue.
  - (c) Mettre les recharges dans la facture : le test bière + recharge échoue.
  - (d) Oublier la part offerte : le test de la recharge offerte échoue.
  - (e) Ne pas séparer la part en jetons : le test des jetons échoue.

- [ ] **Step 7 : message de commit proposé** — `feat(compta): vente_a_facturer(), une vente découpée pour un logiciel de facturation`

---

### Task 3 : les ventes à facturer égalent le FEC, compte par compte

**Files :**
- Modify : `tests/pytest/test_fec_equilibre.py` (un test dans `TestFecEquilibre`, après `test_fec_equilibre_sur_le_scenario_complet`)
- Modify : `comptabilite/ventes_a_facturer.py` (ajout de `ventes_a_facturer_de_la_cloture`)

**Interfaces :**
- Produces : `ventes_a_facturer_de_la_cloture(cloture_j, apres_le_numero=None, nombre_au_plus=None) -> list[dict]`. Elle lit les ventes de la plage de la J (`REGLEE`, `EUR`, nature ≠ `CORRECTION`, `numero > apres_le_numero`), triées par numéro, avec `select_related("client", "point_de_vente")` et `prefetch_related("reglements", "ventes_derivees__reglements", Prefetch("articles", <même select_related que ventilation.py l.418-421>))`. Elle appelle `vente_a_facturer` sur chacune et retire les `None`. Elle lit les comptes du plan une fois.

- [ ] **Step 1 : le test rouge**

```python
    def test_ventes_a_facturer_egales_au_fec_compte_par_compte(self):
        """
        Fiche 06-D : le scénario complet, découpé en factures, paiements, virements et
        paiements divers, donne compte par compte les mêmes sommes que le FEC de la J.
        / The full scenario split for invoicing gives the FEC's per-account totals.
        """
        <même préparation que test_fec_equilibre_sur_le_scenario_complet, l.958-972>
        cloture = self._cloturer_la_journee_a(MOMENT_DU_Z)

        soldes_du_fec = {}
        for ecriture in ventiler_cloture(cloture):
            for ligne in ecriture["lignes"]:
                soldes_du_fec[ligne["compte"]] = soldes_du_fec.get(ligne["compte"], 0) + ligne["debit"] - ligne["credit"]

        soldes_des_factures = {}
        def ajouter(compte, montant_au_debit):
            soldes_des_factures[compte.numero_de_compte] = soldes_des_factures.get(compte.numero_de_compte, 0) + montant_au_debit
        for decoupe in ventes_a_facturer_de_la_cloture(cloture):
            for ligne in decoupe["lignes_de_la_facture"]:
                ajouter(ligne["compte"], -ligne["total_ht"])
                if ligne["compte_de_tva"] is not None:
                    ajouter(ligne["compte_de_tva"], -ligne["total_tva"])
            for paiement in decoupe["paiements_de_la_facture"]:
                ajouter(paiement["compte"], paiement["montant"])
            for virement in decoupe["virements"]:
                ajouter(virement["vers"], virement["montant"])
                ajouter(virement["depuis"], -virement["montant"])
            for paiement_divers in decoupe["paiements_divers"]:
                ajouter(paiement_divers["compte_de_tresorerie"], paiement_divers["montant"])
                ajouter(paiement_divers["contrepartie"], -paiement_divers["montant"])

        soldes_du_fec = {numero: solde for numero, solde in soldes_du_fec.items() if solde != 0}
        soldes_des_factures = {numero: solde for numero, solde in soldes_des_factures.items() if solde != 0}
        assert soldes_des_factures == soldes_du_fec
```

Le compte client (411) ne figure pas : la facture le débite, son paiement le crédite. Il est soldé dans chaque vente.

- [ ] **Step 2 : voir rouge** (`ImportError` sur `ventes_a_facturer_de_la_cloture`)
- [ ] **Step 3 : écrire `ventes_a_facturer_de_la_cloture`** (interface ci-dessus)
- [ ] **Step 4 : voir vert** — `docker exec lespass_django poetry run pytest tests/pytest/test_fec_equilibre.py -q`
- [ ] **Step 5 : mutations** : un virement à l'envers (`depuis` et `vers` inversés) ; la contrepartie de la recharge offerte au 419100 au lieu de 623400. Les deux font échouer l'égalité.
- [ ] **Step 6 : message de commit proposé** — `test(compta): ventes à facturer = FEC compte par compte`

---

### Task 4 : la route `GET /api/v2/closures/<uuid>/sales/`

**Files :**
- Modify : `api_v2/permissions.py` (classe `CleAvecLeDroitDesVentes`)
- Modify : `api_v2/views.py` (action `sales` de `ClosureViewSet`, après `entries`)
- Modify : `api_v2/serializers.py` (`VenteAFacturerSerializer`, rendu JSON d'un dict de la tâche 2)
- Modify : `api_v2/openapi-schema.yaml`, `api_v2/GUIDELINES.md` (section comptabilité)
- Test : `tests/pytest/test_api_v2_ventes_comptables.py` (neuf, schéma `test_api_ventes_comptables`)

**Interfaces :**
- Consumes : `ventes_a_facturer_de_la_cloture` (Task 3), `RepartitionImpossible`, `_cloture_a_exporter` (existant), `_reponse_de_refus` et les codes `CODE_DU_REFUS_*` (existants).
- Produces (le contrat lu par le module) :

```json
{
  "closure": "<uuid>", "number": 12, "accountingDate": "2026-10-31",
  "currency": "EUR", "amountUnit": "cent",
  "results": [
    {
      "identifier": "<uuid de la vente>", "orderNumber": 1016, "nature": "sale",
      "relatedSale": {"identifier": "<uuid>", "orderNumber": 1002} | null,
      "customer": {"identifier": "<uuid user>", "email": "alice@exemple.fr"} | null,
      "orderedItem": [
        {"priceIdentifier": "<uuid tarif>" | null, "name": "Bière — Pinte",
         "quantity": "1.000000", "unitPrice": 500, "totalTTC": 500, "totalHT": 417,
         "totalVAT": 83, "vatRate": "20.00",
         "accountingAccount": "707000", "vatAccountingAccount": "445711" | null}
      ],
      "invoicePayments": [{"treasuryAccount": "530000", "method": "CA", "amount": 500}],
      "transfers": [{"fromAccount": "419100", "fromMethod": null, "toAccount": "512100",
                     "toMethod": "CC", "amount": 1000, "label": "Recharge cashless"}],
      "variousPayments": [{"treasuryAccount": "419100", "method": null, "amount": -1000,
                           "counterpartAccount": "623400", "label": "Recharge offerte"}]
    }
  ],
  "nextAfterNumber": 1016 | null
}
```

Les comptes sont publiés **par leur numéro TiBillet**. Le module les convertit avec `numeroDeCompteDolibarr()`, comme pour les écritures. `treasuryAccountLabel` et `accountingAccountLabel` : le libellé du compte, pour que le module crée banque et compte s'ils manquent.

- [ ] **Step 1 : les tests rouges** (outils copiés de `test_api_v2_comptabilite.py` : `_creer_une_cle_d_api(droit_comptabilite, droit_ventes)`, `_vendre_une_entree_a`, `_cloturer_la_journee_a`)

```python
    def test_comptabilite_seule_refusee_avec_ventes_acceptee(self): ...   # 403 puis 200
    def test_j_non_exportable_404(self): ...                              # uuid inconnu, J sans ventes
    def test_une_vente_en_especes_publiee(self):
        # orderNumber, customer null, une ligne au tarif (priceIdentifier = uuid du Price),
        # invoicePayments [{"treasuryAccount": "530000", "method": "CA", "amount": 350}]
    def test_client_publie_par_son_email_seul(self): ...                  # aucune autre clé que identifier, email
    def test_pagination_after_number_et_limit(self): ...                  # 3 ventes, limit=2 → 2 + nextAfterNumber ; puis 1 + null
    def test_after_number_ou_limit_invalide_400(self): ...
    def test_vente_sans_montant_absente(self): ...
    def test_repartition_impossible_409_nomme_la_vente(self): ...
    def test_nombre_de_requetes_fixe(self): ...                           # CaptureQueriesContext, 1 vente puis 5 ventes
```

- [ ] **Step 2 : voir rouge** (404 sur la route `sales`)

- [ ] **Step 3 : la permission**

```python
class CleAvecLeDroitDesVentes(BasePermission):
    """
    La clé doit AUSSI avoir le droit « Ventes » : la route publie l'e-mail des
    acheteurs. À poser après SemanticApiKeyPermission (droit de la route).
    / The key must ALSO have the "sale" right: the route publishes buyers' e-mails.
    """

    message = "API key lacks the sale permission"

    def has_permission(self, request, view):
        cle = get_apikey_valid(view)
        if not cle:
            return False
        return bool(cle.sale)
```

- [ ] **Step 4 : l'action**

```python
    @action(detail=True, methods=["get"], permission_classes=[SemanticApiKeyPermission, CleAvecLeDroitDesVentes])
    def sales(self, request, uuid=None):
        from comptabilite.ventes_a_facturer import RepartitionImpossible, ventes_a_facturer_de_la_cloture
        from laboutik.plan_comptable import CompteComptableManquant, s_assurer_que_le_plan_existe
        from comptabilite.ventilation import date_de_debut_de_service

        cloture, reponse_de_refus = self._cloture_a_exporter(uuid)
        if reponse_de_refus is not None:
            return reponse_de_refus
        <lire after_number (même contrôle regex que list) et limit (1 à 1000, défaut 500) ; 400 sinon>
        s_assurer_que_le_plan_existe()
        try:
            with translation.override("fr"):
                decoupes = ventes_a_facturer_de_la_cloture(cloture, apres_le_numero, limite + 1)
                <garder limite éléments ; nextAfterNumber = numéro du dernier gardé s'il y en avait plus, sinon None>
                resultats = VenteAFacturerSerializer(decoupes, many=True).data
        except CompteComptableManquant as compte_manquant:
            return _reponse_de_refus(str(compte_manquant), CODE_DU_REFUS_COMPTE_MANQUANT, status.HTTP_409_CONFLICT)
        except RepartitionImpossible as repartition_impossible:
            logger.exception(f"API comptable : répartition impossible, clôture {cloture.uuid}")
            return _reponse_de_refus(str(repartition_impossible), CODE_DU_REFUS_ECRITURE_DESEQUILIBREE, status.HTTP_409_CONFLICT)
        return Response({
            "closure": str(cloture.uuid), "number": cloture.numero_sequentiel,
            "accountingDate": date_de_debut_de_service(cloture).isoformat(),
            "currency": "EUR", "amountUnit": "cent",
            "results": resultats, "nextAfterNumber": prochain_numero,
        })
```

Vérifier que `entries` publie la même `accountingDate` que `date_de_debut_de_service` (`export["date_du_nom_du_fichier"]`). Prendre la même source pour les deux.

- [ ] **Step 5 : le sérialiseur** (`serializers.Serializer`, méthode `to_representation(self, decoupe)` qui construit le dict du contrat. `quantity` avec 6 décimales en texte, `vatRate` avec 2 décimales en texte, `relatedSale` depuis `vente.vente_liee`)

- [ ] **Step 6 : voir vert**, puis lancer aussi `test_api_v2_comptabilite.py` et `test_api_v2_catalogue_comptable.py`.

- [ ] **Step 7 : mutations** : retirer `CleAvecLeDroitDesVentes` (le test de droit échoue) ; ajouter `first_name` au client (le test « e-mail seul » échoue) ; retirer `ventes_derivees__reglements` du prefetch (le test du nombre de requêtes échoue).

- [ ] **Step 8 : la doc** : OpenAPI (opération `listClosureSales`, paramètres, 200, 400, 403, 404, 409), GUIDELINES (`sales` dans la section comptabilité), CHANGELOG `CHANGELOG/2026-10-xx-ventes-comptables.md` (modèle : `CHANGELOG/2026-10-15-catalogue-comptable.md`). Une nouvelle chaîne `_()` éventuelle est à signaler pour `makemessages`.

- [ ] **Step 9 : message de commit proposé** — `feat(api): /closures/<uuid>/sales/ — les ventes d'une J pour un logiciel de facturation`

---

## Partie B — Module Dolibarr

Toutes les tâches de la partie B se vérifient avec `docker exec dolibarr-dev-dolibarr-1 php /var/www/html/custom/tibillet/scripts/essai.php`. **Prérequis** : le lieu `lespass` a une J exportable avec des ventes variées. Aujourd'hui, la J n° 2 est refusée à cause du produit « TEST_vente Jus » sans compte : c'est au mainteneur de décider comment la débloquer. Les cas difficiles à obtenir en vrai passent par une réponse **imitée**, comme `CatalogueImite` (essais 16 à 21).

### Task 5 : les tables

**Files :**
- Create : `sql/llx_tibillet_vente_importee.sql`, `sql/llx_tibillet_vente_importee.key.sql`
- Modify : `sql/llx_tibillet_cloture_importee.sql` (colonne `mode` dans le `CREATE`)
- Create : `sql/llx_tibillet_cloture_importee-mode.sql` (`ALTER … ADD COLUMN mode` pour une base déjà installée)

```sql
-- Les ventes TiBillet deja recopiees (mode « articles et ventes »). Garde contre les
-- doublons (vente_uuid) et curseur dans une J (numero_vente).
-- / TiBillet sales already copied.
CREATE TABLE llx_tibillet_vente_importee (
	rowid integer AUTO_INCREMENT PRIMARY KEY NOT NULL,
	entity integer DEFAULT 1 NOT NULL,
	vente_uuid varchar(36) NOT NULL,
	numero_vente integer NOT NULL,
	cloture_uuid varchar(36) NOT NULL,
	fk_facture integer DEFAULT NULL,
	date_import datetime NOT NULL
) ENGINE=innodb;
```

```sql
ALTER TABLE llx_tibillet_vente_importee ADD UNIQUE INDEX uk_tibillet_vente_importee (vente_uuid, entity);
ALTER TABLE llx_tibillet_vente_importee ADD INDEX idx_tibillet_vente_importee_cloture (cloture_uuid, numero_vente);
```

```sql
ALTER TABLE llx_tibillet_cloture_importee ADD COLUMN mode varchar(16) DEFAULT 'ecritures' NOT NULL;
```

- [ ] **Step 1 :** vérifier dans `core/modules/DolibarrModules.class.php::_load_tables` (l.1293-1340) que `llx_tibillet_cloture_importee-mode.sql` est bien lu, et que l'erreur « colonne déjà là » est ignorée à la réactivation (`run_sql`, liste des erreurs acceptées). Sinon, lire `SHOW COLUMNS` dans `modTiBillet::init()` avant l'`ALTER`.
- [ ] **Step 2 :** `noterLaCloture` (`importtibillet.class.php:601`) écrit `mode = 'ecritures'`.
- [ ] **Step 3 :** désactiver puis réactiver le module (`activateModule('modTiBillet')` en CLI, comme en 06-C). Contrôler avec `SHOW COLUMNS` et `SHOW INDEX`. Les essais 1 à 21 restent verts, sauf 1 et 4 tant que la J n° 2 bloque.
- [ ] **Step 4 : message de commit proposé** — `feat(sql): ventes importées, mode de chaque clôture importée`

### Task 6 : `ReglagesTiBillet` — préparer Dolibarr (Q10, D11, D20-D22)

**Files :**
- Create : `class/reglages.class.php`
- Modify : `langs/fr_FR/tibillet.lang`, `langs/en_US/tibillet.lang`
- Test : `scripts/essai.php` (essais 22 à 24)

**Interfaces :**
- Produces :
  - `ReglagesTiBillet::preparer($user) : int` : rend 0, ou -1 avec `$this->error`. Remplit `$this->faits` (phrases de ce qu'il a réglé) et `$this->manques` (ce qui manque encore : `ACCOUNTING_ACCOUNT_CUSTOMER`, `ACCOUNTING_VAT_SOLD_ACCOUNT`, `ACCOUNTING_ACCOUNT_TRANSFER_CASH` vides ; `FAC_FORCE_DATE_VALIDATION`, `INVOICE_CHECK_POSTERIOR_DATE` ou `STOCK_CALCULATE_ON_BILL` allumés ; droit `facture->creer` absent).
  - `ReglagesTiBillet::banquePourLeCompte($numero_tibillet, $libelle, $user) : int` : rowid de `llx_bank_account`. Il lit le lien `TIBILLET_BANQUE_<numero>` ; s'il manque, il cherche une banque avec ce `account_number` ; sinon, il en crée une (`ref` = `TIB<numero>`, `label` = « TiBillet — <libellé> », type 2 si le numéro commence par 53, sinon 1, `country_id` = pays de la société, `date_solde` = maintenant, journal = celui du code `BQ`) et enregistre le lien.
  - `ReglagesTiBillet::idDuCodeDePaiement($moyen_tibillet) : int` : la table de D22 (`CA` → `LIQ`, `CC` → `CB`, `CH` → `CHQ`, `TR` → `VIR`, `SN`/`SP`/`SR` → `VAD`, tout le reste et `null` → `TIB`). `VAD` est activé et `TIB` créé (`type` 2, `active` 1) au premier besoin. Pour une banque de type caisse : toujours `LIQ`.
  - `ReglagesTiBillet::poserLeCompteDeTva($taux, $numero_tibillet) : int` : écrit `accountancy_code_sell` sur le taux **actif** du pays de la société (`llx_c_tva`, `taux` et `fk_pays`), seulement s'il est vide. Il active le taux s'il est inactif. Il ne modifie jamais un compte déjà posé : il le signale dans `manques` s'il diffère.
  - `ReglagesTiBillet::tiersDePassage($user) : int` : la constante `TIBILLET_TIERS_DE_PASSAGE`, sinon le tiers `ref_ext = 'tibillet:client-de-passage'`, sinon il crée « Client de passage TiBillet » (`client=1`, `code_client='auto'`).

- [ ] **Step 1 : essais rouges**
  - 22 : `preparer()` sur la base de dev ; `faits` et `manques` lus. Un second appel n'ajoute rien à `faits`.
  - 23 : `banquePourLeCompte('530000', 'Caisse', $user)` crée une banque de type caisse avec `account_number = numeroDeCompteDolibarr('530000')` et un journal. Un second appel rend le même rowid.
  - 24 : `idDuCodeDePaiement('LE')` donne le code `TIB`, actif ; `'SN'` donne `VAD`, actif ; `'CA'` donne `LIQ`.
  - Ménage à la fin : banques et codes créés par l'essai retirés **seulement** s'ils n'existaient pas avant (rowid noté au début).
- [ ] **Step 2 : voir rouge** (classe absente).
- [ ] **Step 3 : écrire la classe.** Elle hérite de `ImportTiBillet` pour `numeroDeCompteDolibarr`, comme `CatalogueTiBillet`. Le SQL est échappé (`$this->db->escape`, `(int)`), l'entité filtrée (`getEntity('bank_account')`, `getEntity('c_paiement')`).
- [ ] **Step 4 : voir vert.**
- [ ] **Step 5 : mutations** : banque toujours recréée (essai 23) ; `TIB` pour les espèces (essai 24) ; compte de TVA écrasé (essai 22 bis : un compte posé à la main reste).
- [ ] **Step 6 : message de commit proposé** — `feat(reglages): banques, codes de paiement, TVA et tiers de passage préparés par le module`

### Task 7 : le tiers d'un acheteur

**Files :** `class/ventes.class.php` (neuf, méthode `tiersDeLaVente`) ; `scripts/essai.php` (essais 25 et 26).

```php
	/**
	 * Le tiers de la vente : par e-mail, sans tenir compte des majuscules (Q3), le plus
	 * ancien s'il y en a plusieurs ; cree s'il manque, avec l'e-mail comme nom (Q4).
	 * Sans acheteur : le client de passage.
	 * / The sale's third party: by e-mail, oldest first; created if missing.
	 */
	private function tiersDeLaVente($client, $user)
	{
		if (empty($client['email'])) {
			return $this->reglages->tiersDePassage($user);
		}
		$email = trim($client['email']);
		$sql = "SELECT rowid FROM ".$this->db->prefix()."societe";
		$sql .= " WHERE LOWER(email) = '".$this->db->escape(strtolower($email))."'";
		$sql .= " AND entity IN (".getEntity('societe').")";
		$sql .= " ORDER BY rowid ASC LIMIT 1";
		$resql = $this->db->query($sql);
		$ligne = $resql ? $this->db->fetch_object($resql) : null;
		if ($ligne) {
			return (int) $ligne->rowid;
		}
		$tiers = new Societe($this->db);
		$tiers->name = $email;
		$tiers->email = $email;
		$tiers->client = 1;
		$tiers->code_client = 'auto';
		$tiers->typent_id = dol_getIdFromCode($this->db, 'TE_PRIVATE', 'c_typent', 'code', 'id');
		$tiers->ref_ext = 'tibillet:user:'.$client['identifier'];
		$id = $tiers->create($user);
		if ($id <= 0) {
			$this->error = $tiers->error.' '.implode(' ', (array) $tiers->errors);
			return -1;
		}
		return $id;
	}
```

- [ ] Essai 25 (rouge, puis vert) : un e-mail inconnu crée un tiers ; le même e-mail en majuscules rend ce tiers (Review Focus 4) ; deux tiers avec cet e-mail : le plus ancien.
- [ ] Essai 26 : sans client, le tiers de passage.
- [ ] Mutation : `ORDER BY rowid DESC` (essai 25 échoue).
- [ ] Vérifier le nom exact de la propriété de type de tiers dans Dolibarr 24 (`typent_id`, `societe.class.php`).

### Task 8 : l'import d'une vente

**Files :** `class/ventes.class.php` (`importerUneVente`, `creerLaFacture`, `payerLaFacture`, `virer`, `paiementDivers`, `venteDejaImportee`, `noterLaVente`) ; `scripts/essai.php` (essais 27 à 32, avec une réponse **imitée** de `/sales/` : la classe `VentesImitees extends VentesTiBillet`, qui imite seulement les chemins `/api/v2/closures/` et laisse passer les autres).

Le déroulé de `importerUneVente($vente, $cloture, $date_de_la_j, $user)` :

```php
		$this->db->begin();
		$tiers = $this->tiersDeLaVente($vente['customer'], $user);
		// 1. La facture (s'il y a des lignes) : creer, lignes, valider, controler, payer.
		// 2. Les virements internes : deux Account::addline + add_url_line('banktransfert'),
		//    comme compta/bank/transfer.php l.183-207 (LIQ si l'une des banques est une caisse).
		// 3. Les paiements divers : PaymentVarious (montant positif, sens 1 = entree, 0 = sortie),
		//    accountancy_code = compte de contrepartie, type_payment = idDuCodeDePaiement().
		// 4. La ligne dans llx_tibillet_vente_importee.
		// Une erreur a n'importe quelle etape : rollback, $this->error = « Vente n° … : … », -1.
		$this->db->commit();
```

Les règles de la facture :
- `Facture` : `socid`, `date` = la date de la J à midi, `type` = `TYPE_CREDIT_NOTE` si `nature = refund`, sinon standard. `fk_facture_source` = la facture de `relatedSale` si elle est dans `llx_tibillet_vente_importee`, sinon rien (Review Focus 2). `ref_ext` = uuid de la vente. `note_private` = « Vente TiBillet n° … ».
- Une ligne : le produit dont `ref_ext` est `priceIdentifier`. Sans `priceIdentifier`, ou si le produit est introuvable : une **ligne libre** au même libellé, et une phrase dans le résumé. Le compte reste exact, car la ligne est liée par `fk_code_ventilation`. *(La spec §6.1 refusait la vente ; une ligne libre ne bloque pas la nuit et garde le bon compte. À valider par le mainteneur.)*
- Quantité × prix si `calcul_price_total(qty, unitPrice/100, 0, taux, 0, 0, 0, 'TTC', …)` donne `totalTTC`, sinon quantité 1 au `totalTTC`, la quantité dans le libellé (D8). Avoir : quantité positive, Dolibarr met le prix en négatif.
- `fk_code_ventilation` = rowid de `llx_accounting_account` pour `numeroDeCompteDolibarr(accountingAccount)`, dans le plan actif (`versionDuPlanActif()`). Compte de TVA : `ReglagesTiBillet::poserLeCompteDeTva(vatRate, vatAccountingAccount)`.
- Après `validate($user)` : `total_ttc`, `total_ht` et `total_tva` de la facture **égaux** à ceux de TiBillet, au centime. Sinon, on refuse la vente.
- Paiements : un `Paiement` par élément de `invoicePayments` (`amounts[facture] = montant/100`, `paiementid = idDuCodeDePaiement(method)`, `datepaye` = la date de la J) ; `create($user, 1)`, puis `addPaymentToBank($user, 'payment', '(CustomerInvoicePayment)', banquePourLeCompte(...), '', '')`.
- Pendant tout le passage : `$conf->global->MAIN_DISABLE_PDF_AUTOUPDATE = 1`, **en mémoire seulement** (D18).
- **Numéro déjà pris (D24)** : si `validate()` ou `Paiement::create()` échoue sur l'index unique de la référence (`uk_facture_ref`, ou celui de `llx_paiement` ; lire `$this->db->lasterrno()` = `DB_ERROR_RECORD_ALREADY_EXISTS`), on fait `rollback` et on rejoue la vente **une seule fois**. Essai 31 bis : on pose à la main une facture validée portant le prochain numéro, puis on importe : la vente passe au second essai.

- [ ] Essais (rouges, puis verts), avec la réponse imitée :
  - 27 : bière en espèces → une facture validée, payée, liée au 707, TVA au 445711, un paiement `LIQ` sur la banque 530.
  - 28 : bière + recharge en CB → facture de 5 €, un virement 4191 → 512 de 10 €.
  - 29 : vente sans ligne (recharge seule) → aucune facture, un virement, une ligne dans `vente_importee` avec `fk_facture` NULL.
  - 30 : avoir dont la vente liée est importée → `fk_facture_source` posé ; avoir sans vente liée importée → avoir seul (Review Focus 2).
  - 31 : `totalHT` imité faux d'un centime → vente refusée, rien d'écrit (ni facture, ni banque), `$this->error` nomme la vente.
  - 32 : la même vente deux fois → la seconde est ignorée.
  - 31 bis : numéro de facture déjà pris → la vente passe au second essai (D24).
- [ ] Mutations : `fk_code_ventilation` oublié (27) ; pas de contrôle du centime (31) ; pas de garde de doublon (32) ; virement à l'envers (28).

### Task 9 : le passage de la nuit, la page, le README

**Files :** `class/ventes.class.php` (`importerLesVentes`) ; `class/importtibillet.class.php:118` (`passageDeLaNuit`) ; `admin/setup.php` ; `langs/*` ; `README.md` ; `scripts/essai.php` (essais 33 à 36).

`importerLesVentes()` :
1. Garde du mode (`ventes`) et de la configuration ; `ReglagesTiBillet::preparer()`. Si `manques` n'est pas vide : `-1`, et la page liste ce qui manque.
2. `/api/v2/closures/?after_number=<plusGrandNumeroImporte()>` : le curseur est commun aux deux modes (D17).
3. Pour chaque J, dans l'ordre : `/closures/<uuid>/sales/?after_number=<dernière vente importée de cette J>&limit=500`, page après page, puis `importerUneVente` sur chaque vente.
4. Première vente refusée : **arrêt de tout le passage** (D16). Pas de limite par défaut : le passage suit la pagination jusqu'au bout. Limite facultative `TIBILLET_VENTES_PAR_PASSAGE` atteinte : arrêt, et le résumé dit « reste à faire » (D18, révisée le 2026-10-16).
5. J terminée : `noterLaCloture(..., mode='ventes', pieces='')`.
6. Résumé : J importées, factures, avoirs, tiers créés, virements, paiements divers, ventes refusées (la phrase), reste à faire. Passé à `dol_string_nohtmltag` (point 6 de la relecture de 06-C). Gardé dans `TIBILLET_VENTES_RESUME` et `TIBILLET_VENTES_DATE`.

`passageDeLaNuit()` en mode ventes : catalogue (06-C), puis ventes, **seulement si le catalogue n'a pas d'erreur** (D1 : un tarif vendu doit exister).

Page : en mode ventes, section « Ventes de TiBillet » (dernier passage, résumé, bouton « Importer les ventes maintenant »), section « Réglages faits par le module » (`faits`, `manques`), tiers de passage modifiable, banques par compte TiBillet (une liste déroulante par lien `TIBILLET_BANQUE_*`, qui refuse une banque de caisse hors 530 : D11).

- [ ] Essais :
  - 33 : vraie J de dev, passage complet. Une facture par vente à facturer. Σ par compte (factures + paiements + virements + paiements divers, lus en base) = `entries` de la J. Le journal des ventes s'écrit sans ligne à lier.
  - 34 : second passage → rien de neuf.
  - 35 : `TIBILLET_VENTES_PAR_PASSAGE = 2` → coupure, puis reprise sans doublon ni trou de numéro de facture (Review Focus 5).
  - 36 : J déjà importée en écritures → jamais en ventes (D17).
- [ ] Mutations : passage qui continue après une vente refusée ; curseur de J ignoré ; mode non écrit sur la J.
- [ ] README du module : le mode « articles et ventes » complet, les réglages faits par le module, la clé (droits Produits + Comptabilité + Ventes), les essais.
- [ ] Fiche 06-D : statut « codée », un §11 « tests et mutations ». README du chantier : §12 mis à jour. CHANGELOG.
- [ ] Messages de commit proposés :
  - module : `feat(ventes): import des ventes de TiBillet en factures, virements et paiements divers` ;
  - Lespass : avec la tâche 4.

---

## Ordre et dépendances

1 → 2 → 3 → 4 (Lespass, testable seul) ; puis 5 → 6 → 7 → 8 → 9 (module). Les tâches 6 et 7 sont indépendantes l'une de l'autre. La tâche 9 a besoin d'une J de dev exportable (prérequis de la partie B).
