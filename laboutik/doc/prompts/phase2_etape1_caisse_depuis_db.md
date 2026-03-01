# Phase 2, Etape 1 — Caisse depuis la DB (carte primaire + PV)

## Prompt

```
On travaille sur la Phase 2 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 12 + section 15). Etape 1 sur 2 : les vues de navigation.

Les modeles existent (Phase 0 + Phase 1 faites). Lis le plan section 12
et les vues actuelles dans laboutik/views.py.

Contexte :
- CaisseViewSet a 3 actions : list(), carte_primaire(), point_de_vente()
- Actuellement tout est mocke (utils/mockData.py)
- On remplace les appels mock par des queries ORM
- Pattern FALC (skill /django-htmx-readable) : explicite, verbeux

Tache (1 fichier principal : laboutik/views.py) :

1. carte_primaire() (POST) — remplacer le mock par :
   a) CarteCashless.objects.get(tag_id=tag_id) — la carte NFC
   b) CarteMaitresse.objects.get(carte=carte_cashless) — est-ce une carte maitresse ?
   c) carte_maitresse.points_de_vente.all() — PV autorises
   d) Si 1 seul PV → redirect. Si plusieurs → choix.
   e) Si pas CarteMaitresse → erreur (pas autorise)

2. point_de_vente() (GET) — remplacer le mock par :
   a) PointDeVente.objects.prefetch_related('categories', 'products').get(uuid=uuid_pv)
   b) Construire le stateJson depuis Configuration.get_solo() + donnees PV reelles
   c) Tables si accepte_commandes=True : Table.objects.filter(point_de_vente=pv) si applicable

3. Le `state` global mutable (dict en haut du fichier) doit etre remplace par
   une fonction _construire_state(request, point_de_vente) appelee a chaque requete.

4. Nettoyer : supprimer les imports de mockData dans les fonctions modifiees.
   NE PAS supprimer mockData.py (encore utilise par les vues de paiement).

5. Adapter les templates SI les noms de variables du contexte changent
   (verifier les templates views/ask_primary_card.html et views/pv_route.html).

Verification :
docker exec lespass_django poetry run python manage.py check
Lancer le serveur, naviguer vers /laboutik/caisse/ avec une API key valide.

⚠️ NE PAS toucher aux vues de paiement (PaiementViewSet) — c'est l'etape 2.
⚠️ Garder la compatibilite avec HasLaBoutikAccess (permission existante).
```

## Verification

- GET /laboutik/caisse/ → page d'attente carte primaire (200)
- POST carte_primaire avec un tag_id valide → redirect vers le PV
- GET point_de_vente → interface POS avec les vrais produits depuis la DB
- Sans API key → 403

## Modele recommande

Sonnet
