# Compta — Versements et monnaies locales fédérées (à faire après Fedow V2)

> **Status :** spec rédigée, **non commencée**.
> **Pré-requis :** chantier Fedow V2 mature (modèles `fedow_core.Transaction`,
> `BankTransferService`, ViewSet `BankTransfersViewSet`).
> **Date de spec :** 2026-05-18 (session brainstorming).

## 1. Contexte

L'export comptable actuel (FEC, CSV, Excel) lit **uniquement** les `LigneArticle`.
Tout ce qui passe par `fedow_core.Transaction` sans créer de `LigneArticle`
est **invisible** dans la compta TiBillet.

### Trous comptables identifiés (audit 2026-05-18)

| Cas | Trace `LigneArticle` ? | Trace `fedow_core.Transaction` ? |
|---|---|---|
| Recharge wallet fédéré pur (Stripe → asset, sans adhésion) | ❌ | ✅ |
| Trigger d'adhésion qui crédite un asset gift (LG) | ❌ pour la recharge, ✅ pour l'adhésion seule | ✅ |
| Virement bancaire entre tenants (clearance interplaces) | ❌ | ✅ (en V2, modèle `BANK_TRANSFER`) |
| Remboursement de contribution crowdfunding | ❌ pas implémenté | ❌ pas implémenté |

→ Ces opérations existent en pratique (CLAFoutils par exemple) mais ne sont
pas reflétées dans le compte de résultat des tenants. Pour des associations
qui font de la **monnaie locale** ou de la **compensation interplaces**,
c'est un manque structurel.

## 2. Vocabulaire compta — rappel

### Côté émetteur (la CLAF : émet des CLAFoutils contre euros)

Plan comptable recommandé : **165 — Dépôts et cautionnements reçus**
(passif du bilan, dette envers les porteurs de wallet).

| Événement | Écriture |
|---|---|
| User recharge 50 € en CLAFoutils | DÉBIT 512 Banque 50 / CRÉDIT 165XXX Dépôts CLAFoutils 50 |
| User dépense 30 CLAFoutils chez Boulanger | **Aucune écriture côté CLAF.** Sa dette reste à 50 € car les CLAFoutils circulent toujours dans le réseau. |
| CLAF vire 30 € au Boulanger (clearance) | DÉBIT 165XXX Dépôts CLAFoutils 30 / CRÉDIT 512 Banque 30 |

**Invariant :** solde du 165XXX = somme des wallets users non encore dépensés.

### Côté commerçant fédéré (le Boulanger : reçoit des CLAFoutils)

Plan comptable recommandé : **467 — Autres comptes débiteurs ou créditeurs**
(compte de tiers, créance sur le réseau).

| Événement | Écriture |
|---|---|
| Boulanger vend 30 € de pain en CLAFoutils | DÉBIT 467XXX Liaison CLAFoutils 30 / CRÉDIT 707 Ventes 27,84 + 4457 TVA 2,16 |
| Boulanger reçoit 30 € virement de la CLAF | DÉBIT 512 Banque 30 / CRÉDIT 467XXX Liaison CLAFoutils 30 |

**Invariant :** solde du 467XXX = ce que le réseau doit au commerçant.

### Conservation globale du réseau

```
Σ(165XXX émetteurs) − Σ(wallets users actifs) = Σ(467XXX commerçants)
```

## 3. Conséquence : compte de liaison **par asset**

L'utilisateur a la bonne intuition : il faut un compte **par nom d'asset de
monnaie**. Exemples :

```
165100 — Dépôts CLAFoutils en attente (côté CLAF émetteur)
165200 — Dépôts EuskoMonnaie en attente (autre émetteur)
165900 — Dépôts génériques (fallback)

467100 — Liaison commerçant CLAFoutils
467200 — Liaison commerçant EuskoMonnaie
467900 — Liaison commerçant générique (fallback)
```

→ Implique un nouveau mapping côté DB : **Asset UUID → CompteComptable**
(parallèle au `MappingMoyenDePaiement` déjà existant).

## 4. Design (à valider quand on démarre la session)

### 4.1 Modèles à ajouter dans `comptabilite/`

```python
class MappingAsset(models.Model):
    """
    Mappage Asset (fedow_core.Asset.uuid) -> CompteComptable.
    / Maps an Asset UUID to an accounting account.

    Permet de ventiler les LigneArticle avec asset non-null vers le bon
    compte de liaison (165XXX émetteur, 467XXX commerçant).
    """
    asset_uuid = models.UUIDField(unique=True)
    nom_asset = models.CharField(max_length=120)  # cache lisible
    role_tenant = models.CharField(
        max_length=1,
        choices=[
            ('E', "Émetteur (compte 165)"),
            ('C', "Commerçant (compte 467)"),
        ],
    )
    compte = models.ForeignKey(CompteComptable, on_delete=models.PROTECT)
```

### 4.2 Données seed à ajouter (data migration)

Ajouter au plan comptable :
- `165900 — Dépôts en attente (générique)` type=L (nouveau type "Liaison")
- `467900 — Liaison commerçant (générique)` type=L

### 4.3 Modifications de `RapportComptableService`

- Si `ligne.asset` est non-null → utiliser `MappingAsset[asset_uuid]` plutôt
  que `MappingMoyenDePaiement[payment_method]`
- Si pas de mapping pour cet asset → fallback sur 165900 / 467900 + warning

### 4.4 Page admin "Déclarer un versement bancaire"

Porter (ou recréer plus simple) le `BankTransfersViewSet` de V2 :
- Formulaire HTMX : tenant_destinataire, asset, montant, date, référence,
  commentaire
- Crée une `LigneArticle` avec :
  - `pricesold = null`
  - `payment_method = TRANSFER` (TR)
  - `status = VALID`
  - `sale_origin = ADMIN`
  - `asset = asset_uuid` (l'asset concerné par la compensation)
  - `amount = montant_centimes` (positif si on encaisse, négatif si on verse)
  - `qty = 1`

### 4.5 FEC : génération des écritures équilibrées

Adapter `comptabilite/fec.py` :
- Pour une ligne avec `payment_method=TRANSFER` et `asset` non-null :
  - 1 ligne DÉBIT 165XXX ou 512 selon le rôle du tenant
  - 1 ligne CRÉDIT 165XXX ou 512 selon le rôle du tenant
- Sans `asset` : fallback comportement actuel (juste 512)

## 5. Estimation effort

| Tâche | Effort |
|---|---|
| Modèle `MappingAsset` + migration + seed 165/467 | 1h |
| Admin Unfold pour `MappingAsset` (CRUD simple) | 30 min |
| Adapter `RapportComptableService` (asset → compte) | 1h |
| Adapter `comptabilite/fec.py` (contrepartie 165/467) | 1h |
| Adapter `csv_comptable.py` (idem) | 1h |
| ViewSet/admin "Déclarer un versement" (porter V2 light) | 2h |
| Tests pytest (mapping asset, FEC équilibré, action versement) | 2h |
| **Total estimé** | **~8h** (1 session focus ou 2 demi-sessions) |

## 6. Limites connues

- Les **dépenses internes au réseau** (user dépense ses CLAFoutils chez un
  commerçant fédéré) sont déjà tracées en `LigneArticle` (cas `h` :
  `payment_method=LE/LG`, `asset` set). On les ventile naturellement via le
  nouveau `MappingAsset`. Pas de chantier supplémentaire pour ce cas.
- Les **recharges de wallet pur** (Stripe → asset, sans adhésion) restent
  invisibles tant qu'on n'a pas un trigger qui crée une `LigneArticle`. À
  traiter dans une 2e itération éventuelle après cette première.
- Le **remboursement crowd** reste hors scope (pas d'implémentation actuelle
  côté crowds non plus).

## 7. Pré-requis de démarrage

- Chantier Fedow V2 stabilisé sur `lespass-main` (BankTransferService actif)
- Décision : ce chantier se fait **après** que les tenants migrent vers la
  cohabitation V1/V2 ou directement en V2 ?
- Alignement avec le mainteneur sur le choix des comptes (165 vs 467 vs
  autre, format des numéros par asset)

## 8. Historique

- **2026-05-18** : spec rédigée pendant la session brainstorming « démo data
  comptable Option A ». Décision : on fait la démo Option A maintenant (13
  cas créables sans toucher au code), ce chantier-ci attend Fedow V2.
