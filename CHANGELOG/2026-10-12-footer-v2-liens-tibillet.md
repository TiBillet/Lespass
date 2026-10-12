# Pied de page V2 : « Retrouver TiBillet » sans contact, logo France 2030 / V2 footer: "Find TiBillet" without contact, France 2030 logo

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** Dans le pied de page du skin V2, la 3e colonne « Nous trouver » devient « Retrouver TiBillet » et perd le lien « Nous contacter ». Le badge texte « FRANCE 2030 » est remplacé par le logo.
/ In the V2 footer, the 3rd column "Find us" becomes "Find TiBillet" and loses "Contact us". The "FRANCE 2030" text badge becomes the logo.
**Pourquoi / Why :** « Nous trouver » et son email de contact concernaient TiBillet, mais le public les prenait pour ceux du lieu.
/ "Find us" and its contact email were about TiBillet, but visitors took them for the venue's.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/partials/footer.html` | 3e colonne « Retrouver TiBillet » (liste `.footer-liens-tibillet__liste`, sans contact) ; logo France 2030 |
| `seo/templates/seo/partials/tibillet_community_links.html` | Option `sans_contact` : masque « Nous contacter » (les autres footers ne changent pas) |
| `pages/static/V2/css/V2.css` | `.footer-liens-tibillet__liste` (liens du partial, sans padding Bootstrap) ; `.site-footer__logo-france-2030` remplace `.legal-badge` |

i18n : nouvelle chaîne `Retrouver TiBillet` (msgid FR), workflow de traduction à lancer.

---

## Comment tester (a la main) / Manual test
1. Lieu en skin V2 (ou `/?skin_preview=V2`), descendre au pied de page.
2. Trois colonnes : le lieu (Accueil, Mon espace, Aide et contact) ; TiBillet et ses deux boutons ; « Retrouver TiBillet » avec tibillet.coop, Documentation, Matrix, Discord, Mastodon, Github. Pas de « Nous contacter ».
3. En bas à droite : le logo France 2030 (image), plus le badge texte.
4. Mobile (< 62rem) : une seule colonne.
5. Skins classic et faire_festival, et le site public : leur liste de liens garde « Nous contacter ».

### Plan du site dans la colonne du lieu
**Quoi / What :** La 1re colonne du pied de page V2 reprend le menu du lieu (`main_nav`, entrées de premier niveau), entre « Accueil » et « Mon espace ». La page d'accueil CMS (url `/`) est sautée.
/ The V2 footer's first column repeats the venue menu (top-level entries).
**Pourquoi / Why :** Plan du site en pied de page : liens internes sur chaque page (exploration par les moteurs), accès direct aux rubriques en bas de page. Le footer classic le faisait déjà.

**Test :** le pied de page liste les mêmes rubriques que le menu du haut, dans le même ordre ; la page courante porte `aria-current="page"`.
