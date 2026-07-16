# Migration skins — CHANTIER-03 : agenda + détail événement

**Date :** 2026-07-05
**Migration :** Non

## Ce qui a été fait

Les vues agenda et détail événement des deux skins vivent désormais dans
`pages/<skin>/vues/`, résolues par `gabarit_skin()` (fallback classic).
Spec : `TECH_DOC/SESSIONS/SKINS/CHANTIER-03-AGENDA-EVENEMENT.md`.

- 10 templates reunion déplacés (4 vues + 5 partials habillage + la logique de
  recherche vers `commun/agenda/filtres.html`).
- 3 templates faire_festival déplacés (extends directement le shell ff).
- 5 sites de `BaseBillet/views.py` (EventMVT) basculés sur `gabarit_skin()`.
- **Premiers blocs du contrat de skin, FIGÉS** : agenda_carrousel,
  agenda_description, agenda_filtres, agenda_liste, evenement_entete,
  evenement_tags, evenement_description, evenement_reservation,
  evenement_complements + partial `carte_evenement.html`.
- **Changement assumé** : la méthode `embed` (iframe agenda) suivait toujours le
  look reunion — elle suit maintenant le skin du tenant.

## Vérifications déjà réalisées (session 2026-07-04)
- Snapshots avant/après : 0 diff de contenu (9 pages × 2 skins, pages + HTMX).
- retrieve 200 (2 skins), embed 200 (2 skins, ff rend désormais son skin),
  partial_list page 1 et 2 en 200 (77 cartes en page 2).
- 33 pytest event/pages verts ; E2E complets (voir rapport de session).

## Tests à réaliser (mainteneur)

### Test 1 : agenda reunion (lespass)
1. `/event/` : carrousel, description, recherche, tags, liste par jour.
2. Recherche « E2E » → la liste se filtre (HTMX, cible #event_list).
3. « Voir plus d'événements » → page suivante s'ajoute sans recharger.
4. Clic sur un événement → détail (image, tags, tunnel de réservation).

### Test 2 : agenda faire_festival (chantefrein)
Même parcours — look brutaliste intact, réservation OK.

### Test 3 : embed
1. `/event/embed/` sur lespass : liste sans navbar/footer, look reunion.
2. `/event/embed/` sur chantefrein : **look faire_festival** (nouveau —
   avant c'était toujours reunion). Liens en target=_blank.

## Compatibilité
- `get_skin_template` ne sert plus que : home, infos_pratiques,
  le_faire_festival, federation/explorer, membership/list, base/headless
  (déjà redirigés) — suppression au CHANTIER-08.
- Restent sous `reunion/views/event/` : formbricks, reservation_ok, wizard
  (pages fonctionnelles, CHANTIER-06).
