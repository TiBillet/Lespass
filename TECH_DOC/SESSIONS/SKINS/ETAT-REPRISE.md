# Migration Skins — État de reprise

**Dernière mise à jour :** 2026-07-01
**Statut :** PLAN écrit — **aucun code**. En attente du go pour démarrer.

## Où on en est
- Le plan complet est écrit : `PLAN-MIGRATION-SKINS.md`.
- Option retenue : **B — migration complète** de tout le templating public vers
  `pages/<skin>/`, avec doc facile à lire et blocs bien identifiés.
- Les 3 décisions structurantes sont **verrouillées** (voir ci-dessous).

## Décisions prises (verrouillées)
1. **Skin par défaut = `reunion`** — inchangé. `pages/reunion/` n'existe pas → fallback
   `pages/classic/`. Le contenu `reunion/views/*` actuel **devient** le socle
   `pages/classic/`. Zéro migration de données.
2. **Nommage des blocs = FIXE**, documenté une seule fois au CHANTIER-07, versionné.
   Renommer après = casser les skins tiers → interdit.
3. **Chrome non-skinnable par template** — pas de slots dans les modals/tunnels. Ils
   restent des includes partagés dans `BaseBillet/templates/chrome/`. Retouche visuelle
   d'un skin = **CSS global** uniquement (classes sémantiques). Décision réévaluable plus
   tard, mais **hors de ce chantier** (éviter d'alourdir le refacto).

## Prochaine étape (au go)
1. **CHANTIER-01** — resolver unifié `pages.services.gabarit_skin()` + porter
   `reunion/base.html` → `pages/classic/shell.html` (+ faire_festival). Brancher
   `base_template` dessus. *Sécurité : iso-rendu tous tenants.*
2. **CHANTIER-02** — extraction du chrome (modals/offcanvas/filtres) vers
   `BaseBillet/templates/chrome/`. **Le point dur (60-70 % du risque)** — à faire tôt,
   testable seul, zéro changement visible.

Puis CHANTIER-03 (agenda + détail événement), 04 (adhésions), 05 (accueil/infos/réseau),
06 (pages fonctionnelles → héritent du shell), 07 (doc contrat + `demarrer_skin`),
08 (nettoyage `get_skin_template` + vieilles arbos).

## Pièges / rappels
- **Ne JAMAIS casser le skin `reunion`** (défaut, le plus utilisé). Tests Playwright
  agenda / adhésions / **tunnel de paiement** obligatoires avant de merger chaque chantier.
- **`tibillet.css` est chargé par les DEUX skins** (`faire_festival/base.html:77`) — un
  changement `.navbar`/global touche reunion ET faire_festival.
- Le champ `skin` vit sur `pages.ConfigurationSite` (singleton), lu par
  `get_skin_courant()` (`BaseBillet/views.py:107`).
- Deux systèmes **coexistent** pendant la migration (`get_skin_template` ancien +
  `gabarit_skin` nouveau) — pas de big-bang.
- Ne pas faire d'opération git ni de makemessages (mainteneur).

## Fichiers de référence (pour situer le code)
- `BaseBillet/views.py:107` `get_skin_courant`, `:124` `get_skin_template`, `:167`
  `get_context` (`base_template`), `:2316` agenda, `:2679` adhésions.
- `pages/views.py:57` `rendre_page` (résolution `pages/<skin>/page.html`).
- Templates : `BaseBillet/templates/{reunion,faire_festival}/…` (à migrer),
  `pages/templates/pages/{classic,faire_festival}/…` (cible).
