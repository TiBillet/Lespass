# CHANTIERS 07 + 08 — Contrat de skin + nettoyage final

**Statut :** en cours (2026-07-04).

## CHANTIER-07 — Le contrat de skin + `demarrer_skin`
1. **`TECH_DOC/SESSIONS/SKINS/CONTRAT-DE-SKIN.md`** — LE document versionné qui
   fige : l'arborescence d'un skin, les blocs (shell : `offcanvas_globaux`,
   `offcanvas`, `main`… ; vues : `agenda_*`, `evenement_*`, `adhesions_*`), les
   partials du contrat (`navbar`, `footer`, `carte_evenement`), les ids
   d'offcanvas, les variables de contexte fournies par vue, et la règle
   d'autonomie (P3). Une fois publié : on ne renomme plus rien.
2. **Commande `python manage.py demarrer_skin <nom>`** (app pages) : copie
   `pages/templates/pages/classic/` → `pages/templates/pages/<nom>/` (refus si
   le dossier existe, message FALC pas-à-pas pour activer le skin). Comme les
   choices de `ConfigurationSite.skin` sont figées (reunion/faire_festival), la
   commande affiche la marche à suivre pour ajouter la choice — décision
   d'élargir les choices = hors périmètre (mainteneur).
3. Test pytest de la commande (création, refus d'écrasement).

## CHANTIER-08 — Nettoyage
1. Basculer les 3 extends en dur `"reunion/base.html"` (404.html, 500.html,
   crowds/templates/success.html) → `"pages/classic/shell.html"`.
2. Supprimer `get_skin_template` (plus aucun appelant après C5) — 
   `get_skin_courant` RESTE (utilisé par gabarit_skin/pages).
3. Supprimer les arbos `BaseBillet/templates/reunion/` et
   `BaseBillet/templates/faire_festival/` (après C6 il n'y reste que les
   redirections base/headless devenues orphelines + README/maquette ff —
   la maquette ff est déplacée dans TECH_DOC/SESSIONS/SKINS/maquette-ff/).
4. Contrôle final : `rg '"reunion/|faire_festival/' --type html --type py`
   ne doit plus matcher QUE des chemins statics (`static/reunion/…` restants :
   qr-scanner, leaflet, media — assumés, documentés).
5. Tests complets (agent Sonnet) + vérification Chrome finale de TOUT
   (goal : parcours 2 skins + vente Stripe 4242 + recharge tirelire + vente QR).
