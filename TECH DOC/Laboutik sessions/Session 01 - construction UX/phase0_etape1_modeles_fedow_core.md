# Phase 0, Etape 1 — Modeles fedow_core

## Prompt

```
On travaille sur la Phase 0 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 10.1 + section 15, "fedow_core : fondations"). Etape 1 sur 3.

Lis le plan (sections 4, 5, 7, 10.1), le MEMORY.md, et dis-moi ce que
tu comprends avant de coder.

Contexte :
- fedow_core n'existe pas encore. C'est une NOUVELLE app Django.
- Elle doit etre dans SHARED_APPS (schema public, pas d'isolation auto).
- Chaque modele a un champ `tenant` (FK → Customers.Client) pour filtrage.
- L'ancien Fedow est dans OLD_REPOS/Fedow pour reference si besoin.
- Decisions prises : section 16 du plan (toutes decidees).

Tache :

1. Creer l'app fedow_core :
   fedow_core/__init__.py
   fedow_core/apps.py (FedowCoreConfig)
   fedow_core/models.py
   fedow_core/migrations/__init__.py

2. Modeles a creer (cf. plan section 10.1 pour les champs exacts) :

   Asset — 5 categories (TLF, TNF, FED, TIM, FID), uuid PK
   Token — solde d'un wallet pour un asset, UNIQUE(wallet, asset), value en centimes (int)
   Transaction — id BigAutoField PK, uuid UUIDField unique,
     hash nullable, migrated=False, 10 actions (FIRST, CREATION, REFILL, SALE, etc.)
   Federation — M2M tenants + M2M assets

3. Enrichir AuthBillet.Wallet (decision 16.6) :
   - Ajouter public_pem (TextField, nullable, blank=True)
   - Ajouter name (CharField, max_length=100, nullable, blank=True)

4. Enrichir QrcodeCashless.CarteCashless (decision 16.7) :
   - Ajouter wallet_ephemere (OneToOneField → Wallet, nullable, blank=True)

5. Ajouter fedow_core dans SHARED_APPS (TiBillet/settings.py)

6. Lancer :
   docker exec lespass_django poetry run python manage.py makemigrations
   docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
   docker exec lespass_django poetry run python manage.py check

⚠️ Avant de modifier settings.py, montre-moi ce que tu vas changer et attends mon OK.
⚠️ Avant de modifier AuthBillet/models.py ou QrcodeCashless/models.py, lis-les d'abord.
⚠️ Ne cree PAS services.py (etape 2). Ne cree PAS l'admin (etape 3).
```

## Verification

- `manage.py check` passe
- Toutes les migrations appliquees
- En shell Django : `from fedow_core.models import Asset, Token, Transaction, Federation`
- Transaction.id est un BigAutoField (auto-increment geré par Django)
- AuthBillet.Wallet a les nouveaux champs
- CarteCashless a wallet_ephemere

## Modele recommande

**Opus** — modeles critiques, decisions architecturales
