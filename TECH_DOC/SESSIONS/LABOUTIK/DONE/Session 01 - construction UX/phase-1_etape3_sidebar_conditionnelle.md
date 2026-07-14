# Phase -1, Etape 3 — Sidebar conditionnelle

## Prompt

```
On travaille sur la Phase -1 du plan laboutik/doc/PLAN_INTEGRATION.md
Etape 3 sur 3 : la sidebar conditionnelle Unfold.

Les etapes 1 et 2 sont faites : les champs module_* existent, le dashboard
affiche les cartes de modules.

Contexte :
- La sidebar Unfold est configuree dans TiBillet/settings.py (UNFOLD > SIDEBAR)
- Elle contient des sections avec des liens vers les modules admin
- On veut masquer les menus des modules inactifs

Tache (1 fichier : Administration/admin_tenant.py) :

1. Transformer la sidebar statique en sidebar dynamique :
   - Lire Configuration.get_solo() pour connaitre les modules actifs
   - Masquer les entrees de menu des modules inactifs
   - Unfold supporte les fonctions callables pour la sidebar
     (verifier la doc Unfold pour le pattern exact)

2. Mapping modules → menus sidebar :
   - module_billetterie → Event, Product, Price, Reservation
   - module_adhesion → Membership
   - module_crowdfunding → crowds (Initiative, Contribution)
   - module_monnaie_locale → (futur : fedow_core quand il existera)
   - module_caisse → (futur : laboutik quand les modeles existeront)

3. Les menus qui ne dependent d'aucun module restent toujours visibles :
   - Configuration, Users, Client/Domain

4. Verifier :
   - Toggle module_adhesion=False → le menu Adhesion disparait
   - Toggle module_adhesion=True → le menu Adhesion reapparait
   - Les menus Configuration et Users sont toujours la

Ne cree PAS de nouveaux fichiers. Ne touche PAS aux modeles.
```

## Verification

- Toggle un module dans l'admin → le menu apparait/disparait au rechargement
- Les menus "systeme" (Configuration, Users) sont toujours visibles
- Pas de traceback dans les logs du serveur

## Modele recommande

Sonnet
