# Pages légales du tenant root public / Public root tenant legal pages

**Date :** 2026-07-20
**Migration :** Non

## Resume / Summary

**Quoi / What :** Ajout de trois pages légales servies sur le tenant public
(`tibillet.fr`) : `/mentions-legales/`, `/cgu/` et `/confidentialite/`. Liens
ajoutés au pied de page de la landing et au sitemap ROOT.
/ Three legal pages served on the public tenant, linked from the landing footer
and listed in the ROOT sitemap.

**Pourquoi / Why :** Le site n'avait aucune page légale. Les mentions légales sont
imposées par la LCEN (art. 6-III) et la politique de confidentialité par le RGPD
(art. 13-14). Les seuls liens existants pointaient vers la documentation GitHub
Pages — un site tiers non versionné, sans valeur probante pour une acceptation de
CGU.
/ The site had no legal pages at all; the only links pointed to an external,
unversioned documentation site.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/views_legal.py` | **Neuf.** Trois vues, une par document. Constantes de date de mise à jour. |
| `seo/templates/seo/legal/base_legal.html` | **Neuf.** Gabarit commun : H1, date, colonne étroite, navigation inter-documents. |
| `seo/templates/seo/legal/mentions_legales.html` | **Neuf.** Éditeur, directeur de publication, hébergeur, licence, réclamations. |
| `seo/templates/seo/legal/cgu.html` | **Neuf.** 13 articles. L'article 3 pose que TiBillet n'est pas le vendeur des billets. |
| `seo/templates/seo/legal/confidentialite.html` | **Neuf.** Tableau des traitements, cookies, sous-traitants, droits RGPD. |
| `seo/urls.py` | 3 routes ajoutées après `/explorer/`, avant rien (pas de catch-all ici). |
| `seo/views.py` | `sitemap_root_view()` : ajout des 3 URLs légales. |
| `seo/templates/seo/base.html` | Bloc `<nav data-testid="footer-legal">` en bas du pied de page. |
| `tests/pytest/test_seo_pages_legales.py` | **Neuf.** 5 tests : rendu, stabilité des chemins, liens du footer, sitemap. |

### Choix d'architecture / Design decisions

**Gabarits versionnés, pas de contenu en base.** Le CMS à blocs de l'app `pages`
n'est de toute façon pas monté sur le tenant public (`TiBillet/urls_public.py`
n'inclut ni `pages.urls`, ni `admin/`, ni `api/v2/`). Mais même à disposition, un
texte légal doit vivre dans git : il faut pouvoir répondre à « quelles CGU étaient
affichées le 14 mars ? ». Une ligne en base écrase la version précédente sans
trace.

**Périmètre plateforme uniquement.** Les CGU couvrent la relation coopérative ↔
utilisateur. Les conditions de **vente** (rétractation art. L221-28 12°,
remboursement, médiation) relèvent de chaque lieu organisateur et restent à
écrire, au niveau tenant.

**Corps des documents non traduit par gettext.** Un texte juridique ne se traduit
pas chaîne par chaîne : sa version anglaise engagerait la coopérative et demande
une relecture juridique. Seule l'interface (titres de nav, liens de pied de page)
passe par `{% translate %}`. Cette session ajoute donc **7 chaînes traduisibles**
(pied de page + navigation inter-documents) — le workflow i18n est à lancer par le
mainteneur.

### Piege rencontre / Pitfall hit

La syntaxe de commentaire courte de Django (`{# … #}`) ne fonctionne que sur **une
seule ligne**. Étalée sur plusieurs lignes, elle n'est plus un commentaire : Django
parse et exécute son contenu. Les quatre gabarits ont d'abord renvoyé
`TemplateSyntaxError: 'translate' takes at least one argument`, parce que l'en-tête
de documentation citait `{% translate %}` en toutes lettres. Corrigé en passant aux
blocs `{% comment %}`.

Second piège, côté test : `reverse("seo:cgu")` lève `'seo' is not a registered
namespace`. `reverse()` interroge l'urlconf **par défaut** (celui des tenants) ;
l'app `seo` ne vit que dans `TiBillet/urls_public.py`. Il faut passer
`urlconf="TiBillet.urls_public"` explicitement.

---

## Comment tester (a la main) / Manual test

### Test 1 — les trois pages répondent

1. Ouvrir `https://tibillet.localhost/mentions-legales/`
2. Ouvrir `https://tibillet.localhost/cgu/`
3. Ouvrir `https://tibillet.localhost/confidentialite/`
4. Chaque page affiche un H1, une date de mise à jour, et en bas des liens vers les
   deux autres documents.

### Test 2 — accessibilité depuis l'accueil

1. Ouvrir `https://tibillet.localhost/`
2. Descendre tout en bas du pied de page
3. Vérifier les trois liens sous le bandeau France 2030 : « Mentions légales »,
   « CGU », « Confidentialité »
4. Cliquer chacun, vérifier qu'il n'y a pas de 404

### Test 3 — les pages tenant ne sont PAS impactées

1. Ouvrir `https://lespass.tibillet.localhost/`
2. Vérifier que le pied de page tenant n'a **pas** changé (les routes légales
   n'existent que sur le public — y ajouter les liens produirait des 404)

### Test 4 — sitemap

```bash
curl -sk https://tibillet.localhost/sitemap-root.xml | grep -E "legales|cgu|confidentialite"
```
Doit renvoyer les trois `<loc>`.

### Tests automatiques

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_seo_pages_legales.py -q
```
5 tests, tous verts au moment de l'écriture.

---

## A FAIRE AVANT MISE EN PROD / TODO before production

Ces points demandent une décision humaine, ils ne peuvent pas être devinés :

1. **SIRET du siège** — deux numéros ont été fournis (`…00014` et `…00022`). Le
   gabarit utilise `913 628 665 00022`. À confirmer, ou corriger dans
   `mentions_legales.html`.
2. **Médiateur de la consommation** — non renseigné, volontairement. Un médiateur
   doit être un **tiers indépendant** référencé par la CECMC : le directeur de la
   publication ne peut pas être son propre médiateur. Adhésion à prévoir
   (~200-400 €/an) puis ajout d'un article dans les CGU.
3. **Adresse de contact** — les gabarits utilisent `contact@tibillet.re`. Cohérent
   avec le domaine `tibillet.coop` visé par la migration en cours ?
4. **Durées de conservation** — le tableau de `confidentialite.html` propose des
   durées standard (3 ans après dernier contact, 5 ans comptable, 10 ans fiscal,
   12 mois pour les journaux). À confronter aux durées réellement appliquées par
   le code (purge automatique ? aucune ?).
5. **RCS de l'hébergeur** — OVH SAS, 2 rue Kellermann 59100 Roubaix. Vérifier avant
   publication.
6. **Case CGU de l'inscription** — `BaseBillet/templates/fonctionnel/register.html:70`
   et `onboard/templates/onboard/steps/01_identity.html:193` pointent encore vers la
   doc GitHub Pages. À rebrancher sur `/cgu/` du tenant public (URL absolue, puisque
   ces vues tournent sur un tenant).
