# Admin — Encarts Évènements & Adhésions sur la fiche user (accueil festival)

**Date :** 2026-05-24
**Migration :** Non

## Ce qui a été fait

La fiche utilisateur·ice admin (`/admin/AuthBillet/humanuser/<uuid>/change/`)
affiche deux encarts riches, **alimentés en local** (ORM, tenant courant, aucun
appel Fedow), pensés pour l'accueil d'un festival / forum / salon.

### Encart « Évènements » (réservations)
Sous-listes « À venir » / « Passés ». Colonnes :
- **Évènement** — lien cliquable vers la réservation dans l'admin
- **Date** de l'évènement
- **Billets** — `reservation.tickets.count()`
- **Payé** — `reservation.total_paid()` + devise
- **Paiement** — moyen(s) de paiement distincts des lignes payées
- **Statut** — badge couleur (vert payé/validé, bleu gratuit, ambre en attente, rouge annulé)

### Encart « Adhésions »
Sous-listes « En cours » / « Passées ». Colonnes :
- **Adhésion** (produit — tarif) — lien cliquable vers l'adhésion
- **Montant** — `contribution_value` + devise
- **Paiement** — `get_payment_method_display`
- **Échéance** — `deadline`
- **Statut** — badge (vert en cours, rouge annulée, gris autre)

### Modifications
| Fichier | Changement |
|---|---|
| `Administration/admin_tenant.py` | Helpers module-level (`_badge_couleur_reservation`, `_badge_couleur_adhesion`, `_admin_url_basebillet`) ; **fusion des deux `changeform_view`** de `HumanUserAdmin` ; import `NoReverseMatch` |
| `Administration/templates/admin/human_user/right_and_wallet_info.html` | Tableaux enrichis (badges inline, montants tabulaires, liens) |

### ⚠️ Correctif important
`HumanUserAdmin` avait **deux `changeform_view`** (doublon préexistant) : la 2ᵉ
écrasait la 1ʳᵉ en Python. Les encarts affichaient donc « Aucun… » (contexte non
injecté). Les deux méthodes sont désormais **fusionnées** (états des droits +
évènements + adhésions). La logique est encadrée par le `try/except` existant
(gère les POST d'action et les objets absents).

### Détails
- **Périmètre : tenant courant uniquement** (modèles TENANT_APPS).
- **Réservations : toutes** (y compris annulées / non payées), statut affiché.
- **Source FR** pour les nouveaux libellés ; styles de badge inline (le bundle
  Unfold n'inclut pas toutes les classes Tailwind).

## Tests à réaliser (manuel — serveur tenu dans byobu)

### Test 1 : user avec activité
1. Ouvrir la fiche d'un user ayant réservations + adhésions (ex. un user DEMO).
2. **Attendu** : encart « Évènements » avec colonnes évènement (lien), date,
   billets, payé, paiement, statut (badge coloré) ; encart « Adhésions » avec
   adhésion (lien), montant, paiement, échéance, statut.
3. Cliquer un lien → ouvre la réservation / l'adhésion dans l'admin.

### Test 2 : badges & montants
1. Vérifier les couleurs de badge selon le statut (vert/bleu/ambre/rouge).
2. Vérifier l'alignement des montants (chiffres tabulaires, alignés à droite) +
   la devise.
3. Basculer le thème clair/sombre → badges et textes restent lisibles.

### Test 3 : séparation temporelle & vide
1. Évènement futur → « À venir » ; passé → « Passés ».
2. User sans activité → « Aucun évènement… » / « Aucune adhésion… ».

### Test 4 : non-régression droits
1. Les toggles de droits (Administrateur, paiements, créer évènements) doivent
   toujours fonctionner (la fusion a préservé `is_client_admin`, etc.).

## Vérification en base / logique
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
t=Client.objects.get(schema_name='lespass')
with tenant_context(t):
    from BaseBillet.models import Reservation
    r = Reservation.objects.select_related('event').first()
    print(r.event.name, r.tickets.count(), r.total_paid())
"
```

## Performance
- **Requêtes SQL constantes** (≈ 4 quel que soit le nombre de réservations) :
  `prefetch_related('tickets', 'lignearticles', 'paiements__lignearticles')` +
  helper `_lignes_payees_prefetch` (montant + moyens calculés en mémoire, plus
  d'appel `articles_paid()`/`total_paid()`/`tickets.count()` par ligne).
- **Mesuré** : user à 6 réservations → **4 requêtes** (vs ~18 avant). Vérifiable :
  ```bash
  docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
  from django_tenants.utils import tenant_context; from Customers.models import Client
  from django.db import connection; from django.test.utils import CaptureQueriesContext
  t=Client.objects.get(schema_name='lespass')
  with tenant_context(t):
      from BaseBillet.models import Reservation
      from Administration.admin_tenant import _lignes_payees_prefetch
      with CaptureQueriesContext(connection) as ctx:
          for r in Reservation.objects.select_related('event').prefetch_related('tickets','lignearticles','paiements__lignearticles')[:50]:
              _ = _lignes_payees_prefetch(r); _ = len(r.tickets.all())
      print('requêtes:', len(ctx.captured_queries))
  "
  ```
- Adhésions : `select_related('price','price__product')` ; `is_valid()`/`get_deadline()`
  ne requêtent pas si `deadline` est renseigné.
- Pas de test pytest automatique (vue admin + session) — logique et comptage de
  requêtes validés en shell.

## Compatibilité
Additif (hors le correctif du doublon). Aucune migration, aucun appel réseau.
Le bouton « Tirelire » et ses transactions Fedow (72 h) restent inchangés.
