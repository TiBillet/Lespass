# Enrichissement rapports comptables — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrichir le service de rapports comptables et les templates admin/PDF avec tableaux structurés, quantités offertes, prix d'achat, bénéfices, statistiques cartes, noms des monnaies, affichage en euros et i18n complet.

**Architecture:** Enrichissement de 3 méthodes de `RapportComptableService` (totaux, detail_ventes, habitus), nouveau filtre template `|euros`, refonte des templates admin et PDF avec tableaux structurés, ajout `prix_achat` sur Product.

**Tech Stack:** Django 4.x, django-unfold, WeasyPrint, openpyxl, fedow_core, django-tenants

**IMPORTANT:** Ne jamais réaliser d'opération git. Le mainteneur s'en occupe.

---

## Fichiers concernés

### Fichiers à modifier

| Fichier | Changement |
|---------|-----------|
| `BaseBillet/models.py:1139` | Ajouter `prix_achat` IntegerField après `icon_pos` |
| `laboutik/reports.py:75-106` | Enrichir `calculer_totaux_par_moyen()` avec noms monnaies |
| `laboutik/reports.py:112-158` | Enrichir `calculer_detail_ventes()` avec qty_offerts, prix_achat, bénéfice |
| `laboutik/reports.py:325-344` | Enrichir `calculer_habitus()` avec médianes et soldes |
| `Administration/templates/admin/cloture_detail.html` | Refonte complète avec tableaux structurés + `|euros` |
| `laboutik/templates/laboutik/pdf/rapport_comptable.html` | Aligner sur le template admin |
| `Administration/admin/laboutik.py:34-88` | i18n fieldsets LaboutikConfigurationAdmin |
| `Administration/admin/laboutik.py:347-395` | i18n fieldsets ClotureCaisseAdmin + `prix_achat` dans POSProduct |
| `tests/pytest/test_exports.py` | Adapter aux nouvelles structures |

### Fichiers à créer

| Fichier | Rôle |
|---------|------|
| `laboutik/templatetags/laboutik_filters.py` | Filtre `|euros` |
| Migration Product `prix_achat` | IntegerField default=0 |

---

## Task 1 : Filtre template `|euros`

**Files:**
- Create: `laboutik/templatetags/laboutik_filters.py`
- Existing: `laboutik/templatetags/__init__.py` (déjà présent)

- [ ] **Step 1: Créer le filtre**

Créer `laboutik/templatetags/laboutik_filters.py` :

```python
"""
Filtres de template pour l'affichage des montants en euros.
/ Template filters for displaying amounts in euros.

LOCALISATION : laboutik/templatetags/laboutik_filters.py

Utilisation dans un template :
    {% load laboutik_filters %}
    {{ montant_centimes|euros }}
    → "127,50 €"
"""
from django import template

register = template.Library()


@register.filter
def euros(centimes):
    """
    Convertit des centimes (int) en affichage euros.
    12750 → "127,50 €"
    0 → "0,00 €"
    -500 → "-5,00 €"
    None → "0,00 €"
    / Converts cents (int) to euro display.
    """
    from BaseBillet.models import Configuration

    if centimes is None:
        centimes = 0

    # Recuperer le symbole de la monnaie du tenant
    # / Get the tenant's currency symbol
    try:
        config = Configuration.get_solo()
        code_monnaie = config.currency_code or "EUR"
    except Exception:
        code_monnaie = "EUR"

    symbole = "€" if code_monnaie == "EUR" else code_monnaie

    # Conversion centimes → euros avec 2 decimales
    # Separateur decimal : virgule (convention FR)
    # Separateur milliers : espace insecable
    # / Cents → euros with 2 decimals
    # Decimal separator: comma (FR convention)
    # Thousands separator: non-breaking space
    valeur = int(centimes) / 100

    # Formater avec separateur de milliers
    # / Format with thousands separator
    partie_entiere = int(valeur)
    partie_decimale = abs(int(round((valeur - partie_entiere) * 100)))

    # Signe negatif a part pour le formatage
    # / Separate negative sign for formatting
    signe = "-" if valeur < 0 else ""
    partie_entiere_abs = abs(partie_entiere)

    # Separateur milliers avec espace insecable (U+00A0)
    # / Thousands separator with non-breaking space
    entier_formate = f"{partie_entiere_abs:,}".replace(",", "\u00a0")

    return f"{signe}{entier_formate},{partie_decimale:02d} {symbole}"
```

- [ ] **Step 2: Vérifier**

Run:
```bash
docker exec lespass_django poetry run python manage.py check
```

Expected: `System check identified no issues.`

---

## Task 2 : Champ `prix_achat` sur Product + migration

**Files:**
- Modify: `BaseBillet/models.py` (après `icon_pos`, ligne ~1143)

- [ ] **Step 1: Ajouter le champ**

Après le champ `icon_pos` dans `BaseBillet/models.py`, ajouter :

```python
    # Prix d'achat unitaire en centimes (uniquement pour les articles POS).
    # Utilise pour le calcul du benefice estime dans les rapports de cloture.
    # / Unit purchase price in cents (POS articles only).
    # Used for estimated profit calculation in closure reports.
    prix_achat = models.IntegerField(
        default=0,
        verbose_name=_("Purchase price (cents)"),
        help_text=_(
            "Prix d'achat unitaire en centimes. "
            "Utilise pour le calcul du benefice estime. "
            "/ Unit purchase price in cents. "
            "Used for estimated profit calculation."
        ),
    )
```

- [ ] **Step 2: Ajouter `prix_achat` dans l'admin POSProduct**

Chercher le fieldset POS dans l'admin de `POSProduct` ou `ProductAdmin` dans `Administration/admin/` et ajouter `prix_achat` dans le fieldset approprié (celui qui contient `methode_caisse`, `couleur_texte_pos`, etc.).

- [ ] **Step 3: Générer et appliquer la migration**

Run:
```bash
docker exec lespass_django poetry run python manage.py makemigrations BaseBillet --name prix_achat_product
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
```

---

## Task 3 : Enrichir `calculer_totaux_par_moyen()` — noms monnaies

**Files:**
- Modify: `laboutik/reports.py:75-106`

- [ ] **Step 1: Lire le code actuel et enrichir**

Remplacer la méthode `calculer_totaux_par_moyen()` (lignes 75-106 de `reports.py`).

Le nouveau code doit :
1. Garder les 4 totaux existants (especes, carte_bancaire, cashless, cheque)
2. Ajouter `cashless_detail` : ventiler le cashless par asset (via `LigneArticle.asset` → `fedow_core.Asset.name`)
3. Ajouter `currency_code` depuis `Configuration.currency_code`

```python
    def calculer_totaux_par_moyen(self):
        """
        Especes (CA), CB (CC), cashless (LE+LG), cheque (CH), total.
        Enrichi avec le detail cashless par asset et le code devise.
        / Cash, credit card, cashless, check, total.
        Enriched with cashless detail by asset and currency code.
        """
        total_especes = self.lignes.filter(
            payment_method=PaymentMethod.CASH,
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_carte_bancaire = self.lignes.filter(
            payment_method=PaymentMethod.CC,
        ).aggregate(total=Sum('amount'))['total'] or 0

        # NFC / cashless : LOCAL_EURO (monnaie fiduciaire) + LOCAL_GIFT (cadeau)
        # / NFC / cashless: LOCAL_EURO (fiat) + LOCAL_GIFT (gift)
        total_cashless = self.lignes.filter(
            payment_method__in=[PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT],
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_cheque = self.lignes.filter(
            payment_method=PaymentMethod.CHEQUE,
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_general = total_especes + total_carte_bancaire + total_cashless + total_cheque

        # Detail cashless par asset (nom de la monnaie)
        # / Cashless detail by asset (currency name)
        cashless_detail = []
        lignes_cashless_par_asset = self.lignes.filter(
            payment_method__in=[PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT],
            asset__isnull=False,
        ).values('asset').annotate(
            montant=Sum('amount'),
        ).order_by('-montant')

        from fedow_core.models import Asset as FedowAsset
        for ligne in lignes_cashless_par_asset:
            asset_uuid = ligne['asset']
            montant = ligne['montant'] or 0
            # Recuperer le nom de l'asset / Get asset name
            nom_asset = str(_("Inconnu"))
            code_asset = ""
            try:
                asset_obj = FedowAsset.objects.get(uuid=asset_uuid)
                nom_asset = asset_obj.name
                code_asset = asset_obj.currency_code
            except FedowAsset.DoesNotExist:
                pass
            cashless_detail.append({
                "nom": nom_asset,
                "code": code_asset,
                "montant": montant,
            })

        # Code devise du tenant / Tenant currency code
        config_tenant = Configuration.get_solo()
        code_devise = config_tenant.currency_code or "EUR"

        return {
            "especes": total_especes,
            "carte_bancaire": total_carte_bancaire,
            "cashless": total_cashless,
            "cashless_detail": cashless_detail,
            "cheque": total_cheque,
            "total": total_general,
            "currency_code": code_devise,
        }
```

- [ ] **Step 2: Vérifier**

Run:
```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 4 : Enrichir `calculer_detail_ventes()` — qty offerts + prix achat + bénéfice

**Files:**
- Modify: `laboutik/reports.py:112-158`

- [ ] **Step 1: Remplacer la méthode**

La méthode actuelle agrège par produit/catégorie/tva. Le nouveau code doit :
1. Séparer `qty_vendus` (payé en EUR/CB/cheque) et `qty_offerts` (payé en LOCAL_GIFT/EXTERIEUR_GIFT)
2. Ajouter `prix_achat_unit` depuis `Product.prix_achat`
3. Calculer `cout_total = prix_achat_unit * qty_total`
4. Calculer `benefice = total_ht - cout_total`

```python
    def calculer_detail_ventes(self):
        """
        Par article avec qty vendus/offerts, CA TTC/HT, TVA, cout, benefice.
        Groupe par categorie.
        / By article with sold/gifted qty, revenue incl./excl. tax, VAT, cost, profit.
        Grouped by category.
        """
        # Agreger par produit, categorie, TVA et moyen de paiement
        # On separe les paiements cadeau (LOCAL_GIFT, EXTERIEUR_GIFT) des paiements normaux
        # / Aggregate by product, category, VAT and payment method
        # Separate gift payments from normal payments
        produits_agreg = self.lignes.values(
            'pricesold__productsold__product__name',
            'pricesold__productsold__product__categorie_pos__name',
            'pricesold__productsold__product__prix_achat',
            'vat',
            'payment_method',
        ).annotate(
            total_ttc=Sum('amount'),
            total_qty=Sum('qty'),
        ).order_by(
            'pricesold__productsold__product__categorie_pos__name',
            'pricesold__productsold__product__name',
        )

        # Methodes de paiement "cadeau" / Gift payment methods
        methodes_cadeau = [PaymentMethod.LOCAL_GIFT]
        # Ajouter EXTERIEUR_GIFT si le choix existe
        # / Add EXTERIEUR_GIFT if the choice exists
        if hasattr(PaymentMethod, 'EXTERIEUR_GIFT'):
            methodes_cadeau.append(PaymentMethod.EXTERIEUR_GIFT)

        # Regrouper par (categorie, produit) en separant vendus/offerts
        # / Group by (category, product) separating sold/gifted
        cle_articles = {}
        for ligne in produits_agreg:
            nom_categorie = ligne['pricesold__productsold__product__categorie_pos__name'] or str(_("Sans catégorie"))
            nom_produit = ligne['pricesold__productsold__product__name'] or str(_("Inconnu"))
            prix_achat_unit = ligne['pricesold__productsold__product__prix_achat'] or 0
            total_ttc = ligne['total_ttc'] or 0
            total_qty = float(ligne['total_qty'] or 0)
            taux_tva = float(ligne['vat'] or 0)
            moyen_paiement = ligne['payment_method']

            cle = f"{nom_categorie}|{nom_produit}|{taux_tva}"
            if cle not in cle_articles:
                cle_articles[cle] = {
                    "categorie": nom_categorie,
                    "nom": nom_produit,
                    "taux_tva": taux_tva,
                    "prix_achat_unit": prix_achat_unit,
                    "qty_vendus": 0.0,
                    "qty_offerts": 0.0,
                    "ttc_vendus": 0,
                    "ttc_offerts": 0,
                }

            if moyen_paiement in methodes_cadeau:
                cle_articles[cle]["qty_offerts"] += total_qty
                cle_articles[cle]["ttc_offerts"] += total_ttc
            else:
                cle_articles[cle]["qty_vendus"] += total_qty
                cle_articles[cle]["ttc_vendus"] += total_ttc

        # Construire la structure finale par categorie
        # / Build final structure by category
        categories = {}
        for cle, article in cle_articles.items():
            nom_categorie = article["categorie"]
            qty_total = article["qty_vendus"] + article["qty_offerts"]
            total_ttc = article["ttc_vendus"] + article["ttc_offerts"]
            taux_tva = article["taux_tva"]

            # Calcul HT depuis TTC : HT = TTC / (1 + taux/100)
            # / Compute HT from TTC: HT = TTC / (1 + rate/100)
            if taux_tva > 0:
                total_ht = int(round(total_ttc / (1 + taux_tva / 100)))
            else:
                total_ht = total_ttc
            total_tva = total_ttc - total_ht

            # Cout total et benefice estime
            # / Total cost and estimated profit
            cout_total = article["prix_achat_unit"] * int(qty_total)
            benefice = total_ht - cout_total

            if nom_categorie not in categories:
                categories[nom_categorie] = {"articles": [], "total_ttc": 0}

            categories[nom_categorie]["articles"].append({
                "nom": article["nom"],
                "qty_vendus": article["qty_vendus"],
                "qty_offerts": article["qty_offerts"],
                "qty_total": qty_total,
                "total_ttc": total_ttc,
                "total_ht": total_ht,
                "total_tva": total_tva,
                "taux_tva": taux_tva,
                "prix_achat_unit": article["prix_achat_unit"],
                "cout_total": cout_total,
                "benefice": benefice,
            })
            categories[nom_categorie]["total_ttc"] += total_ttc

        return categories
```

- [ ] **Step 2: Vérifier**

Run:
```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 5 : Enrichir `calculer_habitus()` — statistiques cartes

**Files:**
- Modify: `laboutik/reports.py:325-344`

- [ ] **Step 1: Remplacer la méthode**

```python
    def calculer_habitus(self):
        """
        Statistiques cartes NFC : nb cartes, panier moyen, medianes, soldes wallets.
        / NFC card stats: card count, average basket, medians, wallet balances.
        """
        import statistics

        # Depenses par carte dans la periode / Spending per card in period
        depenses_par_carte = list(
            self.lignes.filter(
                carte__isnull=False,
            ).values('carte').annotate(
                total=Sum('amount'),
            ).values_list('total', flat=True)
        )

        nb_cartes = len(depenses_par_carte)
        total = sum(d or 0 for d in depenses_par_carte)
        panier_moyen = int(round(total / nb_cartes)) if nb_cartes > 0 else 0

        # Mediane des depenses / Median spending
        depense_mediane = 0
        if nb_cartes > 0:
            depense_mediane = int(statistics.median(depenses_par_carte))

        # Recharges par carte dans la periode / Top-ups per card in period
        recharges_par_carte = list(
            self.lignes.filter(
                carte__isnull=False,
                pricesold__productsold__product__methode_caisse__in=[
                    Product.RECHARGE_EUROS, Product.RECHARGE_CADEAU, Product.RECHARGE_TEMPS,
                ],
            ).values('carte').annotate(
                total=Sum('amount'),
            ).values_list('total', flat=True)
        )

        recharge_mediane = 0
        if recharges_par_carte:
            recharge_mediane = int(statistics.median(recharges_par_carte))

        # Soldes des wallets lies aux cartes actives (via fedow_core.Token)
        # / Wallet balances for active cards (via fedow_core.Token)
        reste_moyenne = 0
        med_on_card = 0
        try:
            from fedow_core.models import Token as FedowToken, Asset as FedowAsset

            cartes_actives_ids = self.lignes.filter(
                carte__isnull=False,
            ).values_list('carte', flat=True).distinct()

            # Recuperer les wallets via CarteCashless.user.wallet
            # / Get wallets via CarteCashless.user.wallet
            from QrcodeCashless.models import CarteCashless
            wallets_ids = CarteCashless.objects.filter(
                pk__in=cartes_actives_ids,
                user__isnull=False,
                user__wallet__isnull=False,
            ).values_list('user__wallet', flat=True)

            # Soldes en monnaie locale (TLF) / Balances in local currency (TLF)
            soldes = list(
                FedowToken.objects.filter(
                    wallet__in=wallets_ids,
                    asset__category=FedowAsset.TLF,
                ).values_list('value', flat=True)
            )

            if soldes:
                reste_moyenne = int(round(sum(soldes) / len(soldes)))
                med_on_card = int(statistics.median(soldes))
        except Exception:
            # fedow_core pas encore actif ou pas de donnees
            # / fedow_core not yet active or no data
            pass

        # Nouveaux membres dans la periode / New members in period
        from BaseBillet.models import Membership
        nouveaux_membres = Membership.objects.filter(
            date_added__gte=self.debut,
            date_added__lte=self.fin,
        ).count()

        return {
            "nb_cartes": nb_cartes,
            "total": total,
            "panier_moyen": panier_moyen,
            "depense_mediane": depense_mediane,
            "recharge_mediane": recharge_mediane,
            "reste_moyenne": reste_moyenne,
            "med_on_card": med_on_card,
            "nouveaux_membres": nouveaux_membres,
        }
```

- [ ] **Step 2: Vérifier**

Run:
```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 6 : Template admin `cloture_detail.html` — refonte complète

**Files:**
- Modify: `Administration/templates/admin/cloture_detail.html`

- [ ] **Step 1: Réécrire le template complet**

Le template doit :
1. Charger `{% load i18n laboutik_filters %}`
2. Utiliser `{{ montant|euros }}` partout au lieu de `{{ montant }} c`
3. Avoir un tableau structuré dédié pour chaque section (plus de `pprint`)
4. Toutes les strings en `{% translate %}`

Les 13 sections structurées :
- **Section 1 (totaux_par_moyen)** : tableau Moyen/Montant + sous-tableau cashless_detail
- **Section 2 (detail_ventes)** : par catégorie → tableau Produit/Vendus/Offerts/HT/TVA/TTC/Coût/Bénéfice
- **Section 3 (tva)** : tableau Taux/HT/TVA/TTC
- **Section 4 (solde_caisse)** : tableau Ligne/Montant (fond, entrées, solde)
- **Section 5 (recharges)** : tableau Type/Moyen/Montant/Nombre
- **Section 6 (adhesions)** : tableau Moyen/Nombre/Montant
- **Section 7 (remboursements)** : tableau Total/Nombre
- **Section 8 (habitus)** : tableau Statistique/Valeur (8 lignes)
- **Section 9 (billets)** : tableau Événement/Nombre/Montant
- **Section 10 (synthese_operations)** : tableau croisé Type × Moyen
- **Section 11 (operateurs)** : placeholder "Pas encore disponible"
- **Section 12 (ventilation_par_pv)** : tableau PV/CA TTC
- **Section 13 (infos_legales)** : tableau Champ/Valeur

Chaque section suit le pattern :
```html
{% with section=rapport.NOM_SECTION %}
{% if section %}
<div style="margin-bottom: 20px;">
    <h3 style="border-bottom: 2px solid #333; padding-bottom: 4px;">{% translate "Titre" %}</h3>
    <table style="width: 100%; border-collapse: collapse;">
        ...
    </table>
</div>
{% endif %}
{% endwith %}
```

Styles inline uniquement (contrainte Unfold). `data-testid="section-NOM"` sur chaque div de section.

Le template fait ~300 lignes. Lire le template actuel avant de le réécrire entièrement.

- [ ] **Step 2: Vérifier dans Chrome**

Naviguer vers une clôture existante via l'admin et vérifier le rendu.

---

## Task 7 : Template PDF `rapport_comptable.html` — aligner sur admin

**Files:**
- Modify: `laboutik/templates/laboutik/pdf/rapport_comptable.html`

- [ ] **Step 1: Réécrire le template PDF**

Même structure que le template admin (Task 6) mais avec CSS d'impression (`@page A4`).
Charger `{% load i18n laboutik_filters %}`.
Utiliser `{{ montant|euros }}` partout.
Toutes les strings en `{% translate %}`.

- [ ] **Step 2: Tester la génération PDF**

Run:
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_exports.py::TestExports::test_export_pdf_genere -v
```

---

## Task 8 : i18n nettoyage admin

**Files:**
- Modify: `Administration/admin/laboutik.py`

- [ ] **Step 1: Corriger les fieldsets de ClotureCaisseAdmin**

Remplacer :
- `'Period'` → `_('Période')`
- `'Totals (cents)'` → `_('Totaux')`
- `'Details'` → `_('Détails')`

- [ ] **Step 2: Vérifier**

Run:
```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 9 : Adapter les tests existants + nouveaux tests

**Files:**
- Modify: `tests/pytest/test_exports.py`
- Modify: `tests/pytest/test_mode_ecole.py`

- [ ] **Step 1: Adapter `test_export_csv_13_sections`**

Le test vérifie que les 13 sections sont présentes. Pas de changement structurel nécessaire — les clés restent les mêmes. Vérifier que le test passe.

- [ ] **Step 2: Adapter `test_export_pdf_genere`**

Le template PDF a changé (chargement de `laboutik_filters`). Vérifier que le test passe.

- [ ] **Step 3: Ajouter un test pour le filtre `|euros`**

Ajouter dans `test_exports.py` :

```python
    @pytest.mark.django_db
    def test_filtre_euros(self):
        """Le filtre euros convertit les centimes en affichage euros.
        / The euros filter converts cents to euro display."""
        from laboutik.templatetags.laboutik_filters import euros

        assert euros(12750) == "127,50 €"
        assert euros(0) == "0,00 €"
        assert euros(-500) == "-5,00 €"
        assert euros(None) == "0,00 €"
        assert euros(1000000) == "10\u00a0000,00 €"
```

- [ ] **Step 4: Ajouter un test pour `qty_offerts` dans detail_ventes**

Ajouter dans `test_mode_ecole.py` ou un nouveau test :

```python
    @pytest.mark.django_db
    def test_detail_ventes_contient_qty_offerts(self, pv, config):
        """Le detail ventes contient qty_vendus et qty_offerts.
        / Sales detail contains sold and gifted quantities."""
        from laboutik.reports import RapportComptableService

        with schema_context(TENANT_SCHEMA):
            now = timezone.now()
            debut = now - timezone.timedelta(hours=1)
            service = RapportComptableService(pv, debut, now)
            detail = service.calculer_detail_ventes()

            # Verifier la structure pour chaque categorie
            # / Check structure for each category
            for categorie_nom, categorie_data in detail.items():
                for article in categorie_data["articles"]:
                    assert "qty_vendus" in article
                    assert "qty_offerts" in article
                    assert "prix_achat_unit" in article
                    assert "benefice" in article
```

- [ ] **Step 5: Ajouter un test pour `calculer_habitus` enrichi**

```python
    @pytest.mark.django_db
    def test_habitus_contient_medianes(self, pv, config):
        """Les habitus contiennent medianes et soldes.
        / Habitus contain medians and balances."""
        from laboutik.reports import RapportComptableService

        with schema_context(TENANT_SCHEMA):
            now = timezone.now()
            debut = now - timezone.timedelta(hours=1)
            service = RapportComptableService(pv, debut, now)
            habitus = service.calculer_habitus()

            assert "depense_mediane" in habitus
            assert "recharge_mediane" in habitus
            assert "reste_moyenne" in habitus
            assert "med_on_card" in habitus
            assert "nouveaux_membres" in habitus
```

- [ ] **Step 6: Lancer tous les tests**

Run:
```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Expected: ~302+ tests PASSED (299 existants + 3 nouveaux), 0 FAILED.

---

## Task 10 : Vérification finale

- [ ] **Step 1: manage.py check**

Run:
```bash
docker exec lespass_django poetry run python manage.py check
```

- [ ] **Step 2: Tests complets**

Run:
```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

- [ ] **Step 3: Vérification Chrome**

Naviguer vers une clôture dans l'admin, cliquer "View report", vérifier :
- Tous les montants en euros (pas en centimes)
- Tableau structuré pour chaque section
- Pas de `pprint` visible
- Strings traduites

- [ ] **Step 4: Tester l'export PDF**

Cliquer "Export PDF" et vérifier le PDF téléchargé.
