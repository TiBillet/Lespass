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
- **CHANTIER-01-RESOLVER-SHELL.md** — spec du chantier 01 (resolver `gabarit_skin` +
  squelettes shell/headless déplacés vers `pages/<skin>/`, anti-drift par héritage).
  **Codé et vérifié le 2026-07-03.**
- **CHANTIER-02-EXTRACTION-COMMUN.md** — spec du chantier 02 (statics + templates
  partagés + offcanvas → `commun/`, 4 lots A/B/C1/C2). **Terminé le 2026-07-04.**
- **CHANTIER-03-AGENDA-EVENEMENT.md** — spec du chantier 03 (agenda + détail
  événement → `pages/<skin>/vues/`, embed, premiers blocs du contrat).
  **Terminé le 2026-07-04.**
- **CHANTIER-04-ADHESIONS.md** — spec du chantier 04 (adhésions →
  `pages/<skin>/vues/`, tunnel HTMX → `commun/adhesion/`, embed).
  **Terminé le 2026-07-04.**
- **CHANTIER-NN-*.md** — (à venir) specs actionables des chantiers suivants.

## Décisions verrouillées (cf. PLAN §8bis + ETAT-REPRISE P1-P5)
1. **Skin par défaut = `reunion`** (fallback → `pages/classic/`, zéro migration data).
2. **Nommage des blocs FIXE** et documenté une fois (versionné) — étendu aux **ids
   des offcanvas** et de leurs corps cibles HTMX.
3. **Chrome non-skinnable par template** (includes monolithiques BaseBillet ;
   retouche possible en CSS global seulement).
4. **P1-P5 validées le 2026-07-03** (détail dans `ETAT-REPRISE.md`) : le dossier
   partagé s'appelle **`commun/`** (pas « chrome »), statics communs
   `static/commun/`, règle d'autonomie des skins (jamais de référence à un autre
   skin), pattern offcanvas unifié, emails hors skin.

- **CHANTIER-05/06/07-08** — specs des chantiers finaux (accueil/infos/réseau,
  pages fonctionnelles → `fonctionnel/`, contrat + `demarrer_skin`, nettoyage).
  **Terminés le 2026-07-04.**
- **CONTRAT-DE-SKIN.md** — LE contrat versionné (v1.0) : arborescence, blocs
  FIGÉS, ids, variables de contexte, règle d'autonomie.
- **maquette-faire-festival/** — archive de la maquette statique ff.

## État
**🎉 MIGRATION TERMINÉE (2026-07-04) — chantiers 01→08 faits.**
Voir `ETAT-REPRISE.md` et `CONTRAT-DE-SKIN.md`.
