# Fedow : relier le wallet du lieu par un vrai lien en base

**Statut :** idée notée le 2026-11-02, spec à écrire. Rien n'est codé. Pas urgent.

## Le besoin
Aujourd'hui, le wallet d'un lieu se reconnaît à son nom. `WalletService.get_or_create_wallet_tenant`
(`fedow_core/services.py:253`) cherche `origin=tenant` et `name="Lieu <schema>"`.

Le but est de remplacer cette étiquette par un lien en base : `Client.wallet`. La note de la
docstring de cette méthode le prévoit déjà.

## Ce qui existe
- `Wallet.name` n'a aucune contrainte d'unicité avec `origin`.
- Personne ne peut choisir ce nom. Tous les noms de wallet sont écrits par le code, avec un
  préfixe `Wallet ...` pour les clients et les cartes. Aucune admin ni API ne le modifie.
- `Asset.wallet_origin` désigne le wallet qui reçoit les ventes cashless. Il doit être le même
  que le wallet du lieu. Le correctif du 2026-11-02 l'assure pour les nouveaux assets
  (`CHANGELOG/2026-11-02-asset-wallet-du-lieu.md`).

## Les deux faiblesses restantes
Elles sont théoriques à ce jour. Aucune ne s'est produite en prod.

1. **Pas d'unicité.** Deux premiers appels simultanés sur un même lieu peuvent créer deux
   wallets du lieu. Les appels suivants lèvent alors `MultipleObjectsReturned`.
2. **Le nom dépend du schéma.** Si `schema_name` change, un second wallet est créé. L'ancien
   reste orphelin, et les assets existants continuent de pointer vers lui.

## Piste
- Ajouter le lien `Client.wallet`, avec une migration sur `Client`.
- Le remplir pour les lieux qui ont déjà un wallet `Lieu <schema>`.
- Le créer une seule fois, quand le lieu passe sur le moteur V2.

## À régler dans la spec
- Que faire des lieux qui n'ont encore aucun wallet `Lieu <schema>` ?
- `FedowConfig.wallet` reste-t-il distinct ? Aucun flux V2 ne le lit aujourd'hui.

## Références
- Audit : `TECH_DOC/SESSIONS/FEDOW_IMPORT/02b-audit-findings-detail.md`, constats « course
  possible sur la création du wallet lieu » (ligne 166) et ligne 394.
