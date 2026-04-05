# Phase 1 — Refactoring modeles controlvanne

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Les modeles controlvanne utilisent les modeles existants de Lespass (Product, CarteCashless, PointDeVente). Les modeles mock (Card, Fut, Configuration maison, HistoriqueFut) sont supprimes. Le suivi des futs est delegue a l'app inventaire (Stock + MouvementStock).

**Architecture:** On reecrit `controlvanne/models.py` pour pointer vers les modeles Lespass existants. On ajoute la categorie FUT sur Product, le type TIREUSE sur PointDeVente, et un proxy FutProduct. `HistoriqueFut` est supprime — le suivi des futs passe par l'inventaire existant.

**Tech Stack:** Django 4.x, django-tenants (TENANT_APPS), django-solo, Unfold admin

**Spec de reference :** `TECH DOC/SESSIONS/CONTROLVANNE/SPEC_CONTROLVANNE.md`

**IMPORTANT :** Ne pas faire d'operations git. Le mainteneur gere git.

---

## Ordre des taches

1. Ajouts cote Lespass (Product, PointDeVente) — zero impact sur l'existant
2. Reecriture des modeles controlvanne
3. Migration qui detruit les anciens modeles
4. Adaptation admin, signaux, sidebar
5. Verification finale

---

### Tache 1 : Ajouter la categorie FUT sur Product + proxy FutProduct

**Fichiers :**
- Modifier : `BaseBillet/models.py`

- [ ] **Step 1 : Ajouter la constante FUT et le choice**

Ligne 1187, ajouter `FUT = "U"` apres `QRCODE_MA = "Q"`.

Dans `CATEGORIE_ARTICLE_CHOICES`, ajouter apres BADGE :
```python
        # Fut de boisson pour tireuse connectee (controlvanne)
        # / Beverage keg for connected tap (controlvanne)
        (FUT, _("Keg (connected tap)")),
```

- [ ] **Step 2 : Ajouter le proxy FutProduct**

Apres la classe `POSProduct` :
```python
class FutProduct(Product):
    """Proxy pour afficher uniquement les produits fut (tireuses) dans l'admin.
    Proxy to display only keg products in admin.
    Les infos biere (brasseur, type, degre) vont dans long_description.
    Beer info (brewer, type, ABV) goes in long_description.
    Meme table, zero migration."""

    class Meta:
        proxy = True
        verbose_name = _("Keg product")
        verbose_name_plural = _("Keg products")
```

- [ ] **Step 3 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

---

### Tache 2 : Ajouter le type TIREUSE sur PointDeVente

**Fichiers :**
- Modifier : `laboutik/models.py`

- [ ] **Step 1 : Ajouter la constante et le choice**

Apres `AVANCE = 'V'` :
```python
    # Tireuse connectee — accepte uniquement le paiement cashless NFC
    # / Connected tap — accepts only NFC cashless payment
    TIREUSE = 'I'
```

Dans `COMPORTEMENT_CHOICES`, ajouter :
```python
        (TIREUSE, _('Connected tap')),
```

- [ ] **Step 2 : Creer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations laboutik --name add_tireuse_comportement
```

- [ ] **Step 3 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

---

### Tache 3 : Reecrire controlvanne/models.py

Tache centrale. Les modeles supprimes : Card, Fut, Configuration maison, HistoriqueFut.
Les modeles gardes/modifies : Debimetre, CarteMaintenance, TireuseBec, RfidSession, 4 proxy.

**Fichiers :**
- Reecrire : `controlvanne/models.py`

- [ ] **Step 1 : Reecrire le fichier complet**

Modeles dans le nouveau fichier :

**Configuration** — `SingletonModel` (django-solo), vide pour l'instant (champs a venir).

**Debimetre** — inchange (name, flow_calibration_factor).

**CarteMaintenance** — OneToOne vers `CarteCashless`, M2M vers `TireuseBec`, champs `produit` et `notes`.

**TireuseBec** — modifications :
- `uuid` PK, `nom_tireuse`, `enabled`, `notes` : inchanges
- `point_de_vente` : OneToOne vers `laboutik.PointDeVente`, nullable
- `fut_actif` : FK vers `BaseBillet.Product` avec `limit_choices_to={'categorie_article': 'U'}`
- `debimetre` : FK vers `Debimetre`, inchange
- `pairing_device` : FK vers `discovery.PairingDevice`, nullable
- `reservoir_ml`, `seuil_mini_ml`, `appliquer_reserve` : inchanges
- Supprimes : `monnaie`, `prix_litre_override`
- Proprietes `liquid_label`, `prix_litre` : adaptees pour lire depuis Product/Price
- `reservoir_max_ml` : lit la quantite depuis `Stock` du `fut_actif` (inventaire), fallback sur `reservoir_ml`

**RfidSession** — modifications :
- `carte` : FK vers `CarteCashless` (remplace `card` FK vers Card)
- `ligne_article` : FK nullable vers `BaseBillet.LigneArticle`
- Supprimes : `card`, `balance_avant`, `balance_apres`, `charged_units`, `unit_label_snapshot`, `unit_ml_snapshot`
- Tout le reste inchange

**4 proxy** : SessionCalibration, HistoriqueMaintenance, HistoriqueTireuse, HistoriqueCarte — inchanges.

**Modeles supprimes** : Card, Fut, Configuration (maison), HistoriqueFut.

- [ ] **Step 2 : Verifier la syntaxe**

```bash
docker exec lespass_django poetry run python -c "import controlvanne.models"
```

---

### Tache 4 : Recreer la migration initiale

- [ ] **Step 1 : Reverter les migrations controlvanne**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas controlvanne zero --executor=multiprocessing
```

- [ ] **Step 2 : Supprimer l'ancien fichier**

```bash
rm /home/jonas/TiBillet/dev/Lespass/controlvanne/migrations/0001_initial.py
```

- [ ] **Step 3 : Generer la nouvelle migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations controlvanne --name initial
```

- [ ] **Step 4 : Appliquer toutes les migrations**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

- [ ] **Step 5 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run python /DjangoFiles/manage.py showmigrations controlvanne
```

---

### Tache 5 : Simplifier les signaux

**Fichiers :**
- Reecrire : `controlvanne/signals.py`

L'ancien `signals.py` gerait :
- Detection changement de fut → creation HistoriqueFut → decrementation stock Fut
- Push WebSocket apres save TireuseBec

Le nouveau `signals.py` garde uniquement :
- Detection changement de `fut_actif` (FK Product) → init `reservoir_ml` depuis `Stock.quantite` du Product
- Push WebSocket apres save TireuseBec (inchange)

Supprime :
- Tout ce qui touche a `HistoriqueFut` (modele supprime)
- Decrementation `Fut.quantite_stock` (delegue a inventaire)

---

### Tache 6 : Adapter l'admin controlvanne

**Fichiers :**
- Reecrire : `controlvanne/admin.py`

Supprimer : `CardAdmin`, `FutAdmin`, `HistoriqueFutAdmin`, `HistoriqueFutInline`.
Adapter : `TireuseBecAdmin`, `RfidSessionAdmin`, `CarteMaintenanceAdmin`.
Ajouter : `FutProductAdmin` (proxy admin pour les produits fut).

---

### Tache 7 : Adapter la sidebar

**Fichiers :**
- Modifier : `Administration/admin/dashboard.py`

Supprimer de la sidebar : Cards, Keg history, Sessions (redondant avec Tap history).
Adapter : Kegs → pointe vers `FutProduct`.

Entrees finales :
1. Taps (TireuseBec)
2. Keg products (FutProduct)
3. Flow meters (Debimetre)
4. Maintenance cards (CarteMaintenance)
5. Tap history (HistoriqueTireuse)
6. Calibration (SessionCalibration)
7. Configuration (Configuration singleton)

---

### Tache 8 : Verification finale

- [ ] **Step 1 : System check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Step 2 : Tests existants (non-regression)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --timeout=120
```

- [ ] **Step 3 : Test de fumee admin**

1. Dashboard → activer module tireuse
2. Sidebar → Taps → creer une tireuse
3. Verifier que FutProduct fonctionne (creer un produit fut)
4. Verifier que CarteMaintenance demande une CarteCashless

---

## Resume des fichiers modifies

| Fichier | Changement |
|---------|------------|
| `BaseBillet/models.py` | +constante FUT, +choice, +proxy FutProduct |
| `laboutik/models.py` | +constante TIREUSE, +choice |
| `laboutik/migrations/XXXX_add_tireuse_comportement.py` | migration auto |
| `controlvanne/models.py` | reecriture complete (suppression Card, Fut, HistoriqueFut, Config maison) |
| `controlvanne/migrations/0001_initial.py` | nouvelle migration initiale |
| `controlvanne/signals.py` | simplifie (plus de HistoriqueFut, stock delegue a inventaire) |
| `controlvanne/admin.py` | adaptation nouveaux modeles |
| `Administration/admin/dashboard.py` | sidebar reduite a 7 entrees |
