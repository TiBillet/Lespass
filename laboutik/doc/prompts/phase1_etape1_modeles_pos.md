# Phase 1, Etape 1 — Product unifie + modeles POS

## Prompt

```
On travaille sur la Phase 1 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 10.2 + section 15). Etape 1 sur 2 : les modeles.

Lis le plan section 10.2 (Product unifie) et le MEMORY.md.
fedow_core est fait (Phase 0 terminee). Dashboard groupware fait (Phase -1 terminee).

Contexte :
- Decision 16.9 : PAS de modele ArticlePOS separe. Le Product existant est enrichi.
- CategorieProduct dans BaseBillet (pas laboutik) — reutilisable au-dela du POS.
- laboutik est dans TENANT_APPS (isolation auto par schema).
- laboutik/models.py existe mais est vide.
- Les champs exacts sont dans le plan section 10.2.
- Convention : methode_caisse IS NOT NULL = produit disponible en caisse.
- Prix via Price.prix (DecimalField euros). Conversion centimes : int(round(prix * 100)).
- Price.asset FK nullable → fedow_core.Asset (multi-tarif EUR/tokens).

Tache en 2 parties :

PARTIE A — BaseBillet/models.py

1. Creer CategorieProduct (avant la classe Product) :
   - uuid PK, name, icon, couleur_texte (hex), couleur_fond (hex),
     poid_liste, tva FK (SET_NULL), cashless BooleanField
   - Meta : ordering = ('poid_liste', 'name')

2. Enrichir Product avec les champs POS (tous nullable/optionnels) :
   - methode_caisse (CharField 2 chars, 10 choices : VT/RE/RC/TM/AD/CR/VC/FR/BI/FD)
   - categorie_pos (FK → CategorieProduct, SET_NULL, nullable)
   - couleur_texte_pos (CharField 7, hex, nullable)
   - couleur_fond_pos (CharField 7, hex, nullable)
   - groupe_pos (CharField 50, nullable) — groupement de boutons
   - fractionne (BooleanField, default=False)
   - besoin_tag_id (BooleanField, default=False)
   - icon_pos (CharField 50, nullable)

3. Creer proxy POSProduct (apres MembershipProduct) :
   - Filtre : methode_caisse IS NOT NULL
   - Meme table, zero migration

4. Ajouter Price.asset :
   - FK → fedow_core.Asset, SET_NULL, nullable, blank
   - Precedent : Price.fedow_reward_asset fait deja FK tenant → shared
   - Si asset=null → prix en EUR. Si asset set → prix en unites de l'asset.

PARTIE B — laboutik/models.py

5. Creer les modeles (cf. plan section 10.3) :
   - PointDeVente (uuid PK, name, comportement choices D/K/C, service_direct,
     afficher_les_prix, accepte_especes/CB/cheque/commandes, poid_liste, hidden,
     products M2M → Product, categories M2M → CategorieProduct)
   - CarteMaitresse (uuid PK, carte OneToOne → CarteCashless, points_de_vente M2M,
     edit_mode, datetime auto_now_add)
   - CategorieTable (name unique, icon)
   - Table (uuid PK, name, categorie FK, poids, statut choices L/O/S,
     ephemere, archive, position_top/left)

6. Lancer :
   docker exec lespass_django poetry run python manage.py makemigrations BaseBillet
   docker exec lespass_django poetry run python manage.py makemigrations laboutik
   docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
   docker exec lespass_django poetry run python manage.py check

⚠️ NE PAS creer CommandeSauvegarde ni ClotureCaisse (Phase 4 et 5).
⚠️ NE PAS creer l'admin (etape 2).
⚠️ NE PAS modifier les vues laboutik/views.py.
⚠️ Respecter le pattern des proxy existants (TicketProduct, MembershipProduct).
⚠️ help_text avec _(), commentaires bilingues FR/EN (FALC).
```

## Verification

- `manage.py check` passe sans erreur
- Migrations creees et appliquees (BaseBillet/0201 + laboutik/0001)
- En shell Django :
  - `from BaseBillet.models import CategorieProduct, POSProduct, Product, Price`
  - `from laboutik.models import PointDeVente, CarteMaitresse, Table, CategorieTable`
  - `Product._meta.get_field('methode_caisse')` → CharField
  - `Price._meta.get_field('asset')` → ForeignKey
  - `POSProduct._meta.proxy` → True
- Les proxy existants (TicketProduct, MembershipProduct) restent fonctionnels

## Modele recommande

Sonnet — modeles simples, pattern repetitif (enrichissement + proxy)
