# Migration skins — CHANTIER-02 : extraction du commun (lots A, B, C1, C2)

## Ce qui a été fait

Tout le partagé inter-skins déménage vers `commun/` (templates) et
`static/commun/` (statics). Spec : `TECH_DOC/SESSIONS/SKINS/CHANTIER-02-EXTRACTION-COMMUN.md`.

- **Lot A** : 21 statics déplacés (`static/reunion/` → `static/commun/`), 10 fichiers
  de références basculés, `collectstatic --clear`.
- **Lot B** : 6 templates partagés déplacés vers `commun/` (formulaires contact/login/
  réservation, toasts, loading, picture) — faire_festival ne référence plus aucun
  fichier reunion.
- **Lot C1** : 5 offcanvas extraits vers `commun/offcanvas/`, définitions doublées
  reunion/ff unifiées, CSS largeur factorisé (`.offcanvas-tunnel` dans tibillet.css),
  formulaire de recherche → `commun/formulaires/recherche_evenements.html`.
  Tous les ids inchangés (contrat de skin).

### Changements de comportement assumés (unification C1)
- Le tunnel d'adhésion reunion affiche désormais un spinner « Loading… » pendant le
  chargement HTMX (repris du skin faire_festival — avant : panneau vide).
- Titre du tunnel d'adhésion : toujours « Subscribe »/« Adhérer » (le conditionnel
  `product.validate_button_text` était du code mort — `product` n'existe pas hors
  de la boucle produits).

## Vérifications déjà réalisées (session 2026-07-03)
- Snapshots curl avant/après par lot : lot A identique modulo chemins statics,
  lot B identique au bit près, lot C1 diff limité aux commentaires HTML +
  déduplication des `<style>` (revue ligne à ligne).
- 353 pytest verts ×2 runs, E2E complets (voir rapport de session), check 0 issue.
- Vérif visuelle Chrome des 2 skins (home, agenda, adhésions, contrib) +
  réseau sans 404 + parcours offcanvas complets (voir rapport de session :
  vente Stripe 4242, recharge tirelire, QR code mon compte).
- Note : des `srcset` vides sur les événements fédérés de l'agenda = données
  (le cache SEO ne sérialise pas les variations crop, dont les fichiers n'ont
  jamais existé) — préexistant, indépendant du chantier.

## Tests à réaliser (mainteneur)

### Test 1 : les 5 offcanvas, skin reunion (lespass)
1. Navbar → « Aide et contact » : le panneau contact s'ouvre, formulaire envoyable.
2. Navbar → « Connexion » : panneau login (déconnecté) ; `?login=1` l'ouvre tout seul.
3. `/event/` → bouton filtres de la barre de recherche : panneau filtres.
4. Détail d'un événement payant → « Réserver » : tunnel réservation, largeur 800px
   desktop / plein écran mobile, jusqu'au paiement Stripe (4242…).
5. `/memberships/` → carte produit : tunnel adhésion (spinner puis formulaire),
   même vérif largeur.

### Test 2 : idem skin faire_festival (chantefrein)
Panneaux contact/login/réservation/adhésion — mêmes attentes, look brutaliste.

### Test 3 : parcours compte
1. Mon compte → tirelire : recharge en ligne (Stripe 4242) créditée.
2. Mon compte → QR code : scan et vente via qrcode_scan_pay.

## Compatibilité
- Ids d'offcanvas et cibles HTMX inchangés — aucun impact sur les tests Playwright
  existants ni sur les intégrations.
- `#ticketPanel` / `#refundPanel` (pages compte) volontairement hors périmètre
  (CHANTIER-06).
- **Lot C2 fait** : blocs `offcanvas_globaux` (contact+connexion, fin de body) et
  `offcanvas` (tunnels de vue) dans `pages/classic/{shell,headless}.html` ; la
  navbar reunion ne garde que les déclencheurs. Exception faire_festival : le
  panneau contact reste dans `.skin-faire-festival` (CSS scopé). Vérifié :
  déplacement DOM pur (contenu identique), panneaux présents en page complète
  ET en réponse HTMX sur les 2 skins.

### Test 4 (lot C2) : offcanvas après navigation HTMX
1. Sur `/event/`, naviguer vers Adhésions par le menu (swap HTMX du body).
2. Ouvrir « Aide et contact » puis « Connexion » : les panneaux s'ouvrent
   (ils sont re-rendus par headless.html à chaque swap).
