# Phase -1, Etape 2 — Dashboard callback + template

## Prompt

```
On travaille sur la Phase -1 du plan laboutik/doc/PLAN_INTEGRATION.md
Etape 2 sur 3 : le dashboard Unfold avec les cartes de modules.

L'etape 1 est faite : les 5 champs module_* existent sur Configuration.

Contexte :
- dashboard_callback existe dans Administration/admin_tenant.py (ligne ~4872)
  mais est quasi vide (juste "custom_variable": "value")
- Le template Administration/templates/admin/dashboard.html n'existe PAS encore
- Unfold est configure dans TiBillet/settings.py avec DASHBOARD_CALLBACK

Tache (2 fichiers max) :

1. Modifier dashboard_callback dans Administration/admin_tenant.py :
   - Lire Configuration.get_solo()
   - Passer les module_* au contexte du template
   - Passer server_cashless (pour griser la carte Caisse V2)

2. Creer Administration/templates/admin/dashboard.html :
   - Etendre le template dashboard Unfold (regarde comment Unfold fait)
   - Une carte par module : nom, description courte, badge actif/inactif
   - Carte "Caisse & Restauration" : grisee avec message
     "Cashless V1 actif — migration requise" si server_cashless est renseigne
   - Chaque carte doit avoir un lien vers la Configuration pour toggler le module
   - Utiliser les classes Bootstrap/Unfold existantes
   - data-testid sur chaque carte (convention : "dashboard-card-{module}")

3. Le serveur tourne déja, verifie visuellement avec chrome : https://lespass.tibillet.localhost/admin/

Ne touche PAS a la sidebar (etape 3). Ne cree PAS de nouveaux modeles.
```

## Verification

- Le dashboard affiche les 5 cartes de modules
- Un module actif a un badge vert, un inactif a un badge gris
- La carte Caisse est grisee si server_cashless est renseigne
- Les cartes ont des data-testid

## Modele recommande

Sonnet
