# Skin V2 : nettoyage et décisions des points laissés de côté / V2 skin: deferred items cleanup

**Date :** 2026-09-13
**Migration :** Non

## Resume / Summary
**Quoi / What :** traitement des sections 2 (décisions), 3 (nettoyage) et 5
(opérations) de `CHANGELOG/a traiter/v2-da-v1-points-laisses-de-cote.md`.
- **Décision** : la marque « TiBillet » du footer V2 devient un lien vers
  https://tibillet.coop. Les autres décisions sont reportées (liens du footer
  masqués, bouton de don en `href="#"`, mode sombre, boutons et filtres de maquette).
- **Nettoyage** : ancienne carte événement en commentaire supprimée de l'accueil,
  deux gabarits V2 orphelins supprimés, id `badgeOut` rendu unique, deux fichiers
  de maquette obsolètes supprimés.
- **Opérations** : non lancées (docker indisponible ; traductions réservées au
  mainteneur).

/ Footer brand now links to tibillet.coop; other decisions postponed. Removed
the old commented event card, two orphan V2 templates and two obsolete mockup
files; `badgeOut` id made unique. Migrations and translations not run.

**Pourquoi / Why :** solder les points instruits lors de l'intégration de la DA v1
(2026-09-11) qui ne demandaient ni données ni développement.

## Choix d'implementation / Implementation notes
- **Marque du footer** : `<a class="footer-brand__mark" href="https://tibillet.coop"
  target="_blank" rel="noopener">`, URL déjà employée dans les emails
  (`BaseBillet/templates/emails/base.html`). Aucune nouvelle chaîne traduite.
- **Accueil** : dans le commentaire `V2-HERE` des sections masquées, la carte
  événement en dur (remplacée par `cotton/V2/event_card.html`) et les fermetures
  orphelines de son ancienne boucle sont retirées. Les sections « Ce qui se
  prépare » (R2) et « Adhésion & services » (R3) restent en commentaire.
- **`main_old`** : introuvable dans le dépôt, déjà retiré auparavant.
- **Gabarits orphelins** : `pages/V2/partials/carte_evenement.html` et
  `pages/V2/partials/evenement_accordeon.html`. Vérifié avant suppression : aucun
  `include`, aucune occurrence dans le Python (`gabarit_skin()` n'est jamais appelé
  avec ces noms). Le skin classic garde ses propres copies, incluses par chemin
  explicite `pages/classic/…`, donc non concernées.
- **`badgeOut`** : l'id était répété pour chaque badge de la pointeuse. V2 utilise
  `badgeOut-{{ badge.pk }}` (page) et `badgeOut-{{ product.pk }}` (partial renvoyé
  par `Badge.badge_in`). La vue passe désormais `{'product': product}` au partial ;
  le partial classic n'emploie pas la clé. Aucun test ni JS ne lisait `#badgeOut`.
- **Maquette** : `TEMP-tibillet-lespass-main/test-double-nav-v1.html` et `data.js`
  supprimés. Le dossier `TEMP-*` est ignoré par git : suppression locale seulement.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/partials/footer.html` | Marque liée à tibillet.coop |
| `pages/static/V2/css/V2.css` | `.footer-brand__mark` en `inline-block`, souligné au survol |
| `pages/templates/pages/V2/vues/accueil.html` | Ancienne carte événement retirée du commentaire |
| `pages/templates/pages/V2/vues/agenda.html` | Commentaire : `cotton/V2/event_card.html` au lieu du partial supprimé |
| `pages/templates/pages/V2/vues/compte/punchclock.html` | Id `badgeOut-<pk>` |
| `pages/templates/pages/V2/vues/compte/partials/badge_switch.html` | Id `badgeOut-<pk>` |
| `BaseBillet/views.py` | `Badge.badge_in` : `product` passé au partial |
| `pages/templates/pages/V2/partials/carte_evenement.html` | **Supprimé** |
| `pages/templates/pages/V2/partials/evenement_accordeon.html` | **Supprimé** |
| `CHANGELOG/a traiter/v2-da-v1-points-laisses-de-cote.md` | §2 décisions datées, §3 soldé, §5 note |

### Migration
- **Migration necessaire / Migration required :** Non (pour ce changement).
- Rappel, toujours en attente : `pages/migrations/0003` et `0004`
  (`docker exec lespass_django poetry run python manage.py migrate_schemas`).

---

## Comment tester (a la main) / Manual test

Prérequis : un tenant en skin V2.

1. **Footer** : cliquer « TiBillet » → https://tibillet.coop s'ouvre dans un nouvel
   onglet ; soulignement au survol, anneau de focus au clavier.
2. **Accueil et agenda** : les pages s'affichent normalement ; « Load more events »
   ajoute toujours les cartes dans la grille.
3. **Page événement** : s'affiche, accordéon bénévoles compris (il n'utilisait pas le
   gabarit supprimé).
4. **Pointeuse** (Mon espace) avec au moins deux badges : dans l'inspecteur, les
   interrupteurs portent des ids distincts (`badgeOut-<pk>`) et chaque libellé est
   relié au sien.
5. **Skin classic** : pages événement et agenda inchangées.

### Verifs automatiques
- Non lancées pendant la session (docker indisponible).
- `docker exec lespass_django poetry run pytest tests/pytest/ -q`
