# Migration skins — CHANTIER-04 : adhésions

## Ce qui a été fait

La vue adhésions des deux skins vit dans `pages/<skin>/vues/adhesions.html`,
résolue par `gabarit_skin()`. Les 5 partiels HTMX du tunnel (form, 404,
free_confirmed, pending_manual_validation, already_has_membership) sont du
chrome → `commun/adhesion/` (mêmes noms de fichiers, contenu intact — piège
9.8 respecté : ils restent des partiels purs sans base template).
`embed` corrigé comme au C3 (suit le skin du tenant).
Blocs FIGÉS : `adhesions_entete`, `adhesions_tunnel`, `adhesions_grille`,
`adhesions_federees`.
Restent dans reunion pour le C6 : `formbricks.html`, `payment_already_done/
pending`, `payment_link_invalid` (pages autonomes, étendent base_template).

## Vérifications déjà réalisées (session 2026-07-04)
- Snapshots avant/après : 0 diff de contenu (3 pages adhésions × page/HTMX).
- Embed 200 sur les 2 skins (ff rend désormais son skin).
- `/memberships/<uuid>/` renvoie toujours le partiel pur (`<form hx-post…`).
- pytest membership + E2E complets via agent (voir rapport de session).
- Chrome : tunnel des 2 skins + vente Stripe 4242 + recharge + vente QR
  (voir rapport de session).

## Tests à réaliser (mainteneur)

### Test 1 : tunnel d'adhésion complet (reunion)
1. `/memberships/` → carte produit → « Adhérer » : l'offcanvas s'ouvre, le
   formulaire se charge (HTMX dans `#offcanvas-membership`).
2. Tarif payant → Envoyer → Stripe (4242…) → retour avec toast succès.
3. Cas particuliers du tunnel : produit gratuit (free_confirmed), produit à
   validation manuelle (pending_manual_validation), re-souscription au même
   produit (already_has_membership).

### Test 2 : idem faire_festival (chantefrein), look brutaliste.

### Test 3 : embeds
`/memberships/embed/` : lespass = look reunion sans navbar ; chantefrein =
**look faire_festival** (nouveau). Boutons en target=_blank.

### Test 4 : liens de paiement (non déplacés, non-régression)
Un lien de paiement d'adhésion déjà réglé → page « payment already done »
complète avec navbar (elle étend base_template → shell).

## Compatibilité
- Ids `#subscribePanel` / `#offcanvas-membership` inchangés (contrat).
- `get_skin_template` ne sert plus que : home, infos_pratiques,
  le_faire_festival, federation/explorer (CHANTIER-05) + base/headless
  (redirections) — suppression au C8.
