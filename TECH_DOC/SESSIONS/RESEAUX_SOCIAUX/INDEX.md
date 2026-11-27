# RESEAUX_SOCIAUX — Hub du chantier

> **Objet :** Lespass programme et publie seul les annonces des événements sur **Instagram** et
> **Mastodon**, une fois les textes validés par l'admin. Le récap quotidien dit ce qui a été
> programmé et publié.

**Statut :** spec validée par le mainteneur. Plan écrit, relu (Fable) et corrigé. Pas encore de code.
**Date :** 2026-11-27
**Remplace :** la piste [POSTIZ](../POSTIZ/INDEX.md), étudiée puis écartée (SPEC §4).

---

## Documents

| Document | Contenu | Statut |
|---|---|---|
| [SPEC.md](SPEC.md) | Décisions, contraintes d'Instagram et de Mastodon, modèles, onglet de l'événement, programmation, publication, récap, menu. | Validée |
| [PLAN.md](PLAN.md) | 10 tâches en TDD (chantiers 01 à 04). | Relu (Fable) et corrigé |

---

## En une phrase

Une app Django `reseaux_sociaux` (schéma de chaque lieu) : un singleton avec les comptes
connectés, le rythme et les modèles de texte ; un onglet « Réseaux sociaux » dans le formulaire
d'événement ; une tâche Celery qui publie les annonces à leur date.

## Les chantiers

| Chantier | Contenu |
|---|---|
| 01 — Menu | Newsletter passe dans la section « Réseau ». |
| 02 — Socle + Mastodon | Tout le circuit, pour Mastodon seul. |
| 03 — Instagram | Connexion OAuth, jeton, images JPEG, post / carrousel / story. |
| 04 — Récap | Les deux rubriques du récap quotidien. |
| 05 — Mentions du co-organisateur | Après CO_ORGANISATION. |

## Chantier voisin

[CO_ORGANISATION](../CO_ORGANISATION/INDEX.md) : indépendant. Les annonces mentionnent les
comptes du co-organisateur quand il y en a un.
