# CO_ORGANISATION — Hub du chantier

> **Objet :** un lieu choisit un autre lieu TiBillet comme **co-organisateur** d'un événement.
> L'événement apparaît dans les deux agendas, et sa page affiche « Organisé par A et B ».

**Statut :** spec écrite, relue (agent Fable) et corrigée. En attente de validation du mainteneur. Pas encore de code.
**Date :** 2026-11-27

---

## Documents

| Document | Contenu | Statut |
|---|---|---|
| [SPEC.md](SPEC.md) | Le champ, l'agenda du co-organisateur, son cache, « Organisé par » (et le bug existant sur les événements fédérés). | Relue |

---

## En une phrase

Une FK `Event.co_organisateur` vers `Client`. L'agenda de B trouve les événements co-organisés
avec lui dans le cache réseau `AGGREGATE_EVENTS`, comme la fédération par tags.

## Lien avec les autres chantiers

- [RESEAUX_SOCIAUX](../RESEAUX_SOCIAUX/INDEX.md) mentionne les comptes connectés du
  co-organisateur dans les annonces.
- Les deux chantiers sont indépendants : l'un peut être livré sans l'autre.
