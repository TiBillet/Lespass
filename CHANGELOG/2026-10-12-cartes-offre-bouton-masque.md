# Bouton d'adhésion masqué quand la carte a une image / Membership button hidden when the card has an image

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** Les cartes d'offre du skin V2 (`.offer-card`) ont une hauteur minimale (300px, 400px pour les ressources) au lieu d'une hauteur fixe. Le contenu prend la place restante sous l'image.
/ V2 offer cards use a minimum height instead of a fixed one; the content fills the space under the cover.
**Pourquoi / Why :** Sur `/memberships/`, avec une image de couverture, le pied de carte (prix + bouton « Adhérer ») sortait de la carte et était coupé par `overflow: hidden`.
/ With a cover image, the card footer (price + button) overflowed and was clipped.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/static/V2/css/V2.css` | `.offer-card` : `height` → `min-height` ; `.offer-card__cover` : `flex-shrink: 0` ; `.offer-card__content` : `height: 100%` → `flex-grow: 1` |

---

## Comment tester (a la main) / Manual test
### Test 1 — adhésion avec image
1. Tenant en skin V2, un produit adhésion publié **avec** une image.
2. Ouvrir `/memberships/`.
3. Le prix et le bouton « Adhérer » sont visibles en bas de la carte. Le clic ouvre le panneau latéral.

### Test 2 — cartes mélangées
1. Une adhésion avec image, une sans, une avec une longue description.
2. Les cartes d'une même ligne ont la même hauteur. La description reste coupée à 6 lignes.

### Test 3 — autres usages de `.offer-card`
- `/my_account/` → onglet adhésions (carte `compte-adhesion`) : rien n'est coupé.
- Cartes ressources (`offer-card-ressource`) : bouton visible.
