# Migration Skins — Hub permanent

> 🟢 **REPRISE DE SESSION : lire `ETAT-REPRISE.md` en premier** — état, décisions
> verrouillées, prochaine étape, pièges.

Chantier d'architecture : **unifier tout le templating public sous l'app `pages`**
(`pages/<skin>/`), avec fallback automatique sur `pages/classic/`. But : rendre la
**création de skin facile pour tout le monde** — un seul dossier, des blocs identifiés,
zéro code Python.

Principe fondateur : **un skin décrit À QUOI ÇA RESSEMBLE, jamais CE QUE ÇA FAIT.**
Le comportement (paiement, réservation, filtres, modals) reste dans BaseBillet.

## Documents
- **PLAN-MIGRATION-SKINS.md** — le plan complet : vision, état actuel (2 systèmes),
  architecture cible (5 catégories de templates), le **contrat de skin** (blocs
  identifiés), découpage chrome/contenu, les **8 chantiers**, la DX cible, risques.
- **CHANTIER-NN-*.md** — (à venir) specs actionables par chantier, quand on passe au code.

## Décisions verrouillées (cf. PLAN §8bis)
1. **Skin par défaut = `reunion`** (fallback → `pages/classic/`, zéro migration data).
2. **Nommage des blocs FIXE** et documenté une fois (versionné).
3. **Chrome non-skinnable par template** (includes monolithiques BaseBillet ;
   retouche possible en CSS global seulement).

## État
Plan écrit, **aucun code**. Attente du go mainteneur pour démarrer le CHANTIER-01/02.
