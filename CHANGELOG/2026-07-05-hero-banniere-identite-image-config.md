# HERO : bannière d'identité (image depuis la Configuration, actions → CTA)

**Date :** 2026-07-05
**Migration :** Non

## Ce qui a été fait
Le bloc HERO ne porte plus d'image ni de boutons. C'est une bannière d'identité
(titre + sous-titre). L'image de fond est lue **au rendu** depuis la Configuration
du lieu, et les actions passent dans un bloc **CTA** séparé.

### Modifications
| Fichier | Changement |
|---|---|
| `pages/blocs_catalogue.py` | HERO = `titre`, `sous_titre` |
| `pages/templates/pages/classic/partials/bloc_hero.html` | Fond = `config.img` ; sinon recentré sobre |
| `pages/templates/pages/faire_festival/partials/bloc_hero.html` | Image = `config.img` ; plus de badge date |
| `pages/static/pages/css/tb-blocs.css` | HERO imageless centré + fond teinté ; filet supprimé |
| `pages/admin.py` + `templates/admin/pages/bloc/hero_aide_before.html` | Champs HERO réduits + note d'aide |
| `pages/services.py` | `construire_page_accueil` : HERO → PARAGRAPHE (si desc) → CTA |
| `BaseBillet/validators.py` | Passe la description longue du wizard |
| 4 commandes démo + `api_v2/openapi-schema.yaml` | Alignées sur le nouveau HERO |

## Tests à réaliser

### Test 1 — HERO classic AVEC image de fond
1. Sur un tenant classic dont `config.img` est renseignée (ex. lespass) : ouvrir `/`.
2. Attendu : fond photo + carte de contenu à gauche, **sans boutons, sans filet bleu**.

### Test 2 — HERO classic SANS image (recentré sobre)
1. Vider l'image de fond (Paramètres → Image de fond) OU tenant neuf sans image.
2. Ouvrir `/`. Attendu : titre + sous-titre **centrés**, fond légèrement teinté,
   **pas de trou à droite**, pas de filet.

### Test 3 — faire_festival
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py charger_demo_faire_festival --schema=chantefrein`
   (pose le logo « Faire » sur `config.img`).
2. Ouvrir `https://chantefrein.tibillet.localhost/`. Attendu : logo « Faire »
   centré sur le motif « + », sous-titre dessous, **plus de badge date, plus de boutons**.

### Test 4 — Home auto-générée (onboarding)
1. Créer un tenant via le wizard onboard **avec** une description longue.
2. La home est fabriquée **à la fin de la tâche** (`create_tenant_from_draft`),
   juste avant l'email « espace prêt ».
3. Attendu sur `/` : HERO (nom + description courte, image = celle du formulaire
   posée sur `config.img`) → PARAGRAPHE (la description longue saisie) → CTA
   (boutons Agenda/Adhésions selon les modules actifs).
4. Refaire **sans** description longue → le bloc PARAGRAPHE est **présent mais
   vide** (rend rien à l'écran, remplissable ensuite depuis l'admin).

### Test 6 — Image du HERO centrée (écran large)
1. Sur un tenant classic avec `config.img`, élargir la fenêtre (≥ 1800px, hauteur
   réduite). Attendu : l'image reste **centrée H et V**, la carte est centrée
   verticalement — plus de « on ne voit que le haut ».

### Test 7 — Migration tous tenants (déjà appliquée en dev)
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas`
   (migration `BaseBillet 0225`). Idempotente : re-jouable sans effet.
2. Attendu : chaque tenant **sans** home en a une (HERO/PARAGRAPHE/CTA) ; les homes
   existantes (lespass, chantefrein…) **inchangées**.

### Test 5 — Admin
1. Admin → Site web → Blocs → Ajouter. Type = HERO.
2. Attendu : note d'aide bleue « Image de fond du HERO… » visible ; champs limités
   à Titre + Sous-titre (ni image, ni boutons). Changer le type → la note disparaît.

## Vérifications automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -k construire_page_accueil -q
```
(2 tests : ordre HERO/PARAGRAPHE/CTA, HERO sans image/boutons, PARAGRAPHE conditionnel, CTA module-aware.)

## Compatibilité
- **Aucune migration** : les colonnes `image`/`bouton_*` restent sur `Bloc`
  (utilisées par CTA, IMAGE_TEXTE, CARTE…).
- Le hero-avec-image (démo lespass) reste inchangé visuellement (hors filet retiré).
- i18n : lancer `makemessages`/`compilemessages` (nouvelles chaînes de la note admin).
