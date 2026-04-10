# Plan : Skin Faire Festival -> Skin generique avec GrapeJS

## Contexte

La branche `template-faire-festival` (Adrienne) a ete mergee dans main.
Le skin fonctionne mais tout le contenu editorial est hardcode dans les templates.
L'objectif est de rendre ce skin reutilisable par n'importe quel tenant,
avec un contenu editable via l'admin.

Ce plan presuppose que **GrapeJS est integre** comme editeur visuel
(chantier newsletter/landing page a faire avant celui-ci).

## Architecture

### Modele `FaireFestivalConfig` (SingletonModel, TENANT_APPS)

Un modele de configuration specifique au skin, editable dans l'admin Unfold.
Ne s'affiche dans la sidebar que si `config.skin == "faire_festival"`.

**Champs atomiques (donnees courtes) :**
- `tagline` (CharField 250) — phrase d'accroche hero
  - Actuel hardcode : "Le grand rendez-vous toulousain pour reinventer..."
- `horaires` (TextField) — horaires du festival, bloc HTML court
  - Actuel : "JEUDI & VENDREDI 09h-21h / SAMEDI 10h-19h"

**Blocs GrapeJS (contenu editorial riche) :**
- `page_presentation` — contenu de la page "Le Faire Festival"
  - Actuel : 3 sections image+texte (c'est quoi, qui organise, ou)
- `faq` — foire aux questions
  - Actuel : 6 questions/reponses hardcodees dans infos_pratiques.html
- `infos_acces` — infos transport et acces
  - Actuel : voiture/bus/train hardcodes dans infos_pratiques.html
- `partenaires` — liste des partenaires
  - Actuel : noms hardcodes dans le_faire_festival.html

Les blocs GrapeJS sont des TextFields qui stockent le HTML genere par l'editeur.
Le template les rend avec `| safe` (contenu admin-controlled + sanitise par GrapeJS).

### Champ `linkedin` sur Configuration

Ajouter `linkedin = models.URLField(blank=True, null=True)` sur Configuration.
C'est le seul reseau social manquant. Utilise par le footer du skin FF.

### Admin Unfold conditionnel

```python
# Dans admin_tenant.py, section sidebar :
# "Skin Faire Festival" — visible uniquement si config.skin == "faire_festival"
```

Formulaire Unfold avec sections :
- "Accueil" : tagline
- "Infos pratiques" : horaires, infos_acces
- "Page presentation" : page_presentation
- "FAQ" : faq
- "Partenaires" : partenaires

Chaque champ bloc utilise le widget GrapeJS (a definir dans le chantier GrapeJS).

## Etape 1 : Avant GrapeJS (correction immediate)

Remplacer les donnees tenant hardcodees par les champs `config.*` existants :

| Template | Hardcode | Remplacer par |
|---|---|---|
| footer.html:10-11 | Adresse Toulouse | `config.adress`, `config.postal_code`, `config.city` |
| footer.html:33 | URL Facebook | `config.facebook` |
| footer.html:37 | URL LinkedIn | `config.linkedin` (nouveau champ) |
| footer.html:41 | URL Instagram | `config.instagram` |
| footer.html:136-138 | Mentions legales / CGU | `config.legal_documents` |
| infos_pratiques.html:119 | Adresse badge | `config.adress`, `config.city` |
| infos_pratiques.html:294 | Email contact | `config.email` |
| home.html:46 | Phrase d'accroche | `config.short_description` |

Nettoyage :
- Supprimer `maquette/img/` (20 Mo de captures)
- Supprimer `OLD_motion-table.mp4`
- Supprimer les 3 SVG morts (icons8-*.svg)
- Renommer `Fichier-11.png` → noms descriptifs
- Compresser Fichier-15/16/17.png (2 Mo → 300 Ko en WebP)
- Corriger `<p>` mal ferme dans infos_pratiques.html:30
- Ajouter `{% translate %}` sur les textes non traduits

Reseaux sociaux footer : afficher conditionnellement
```html
{% if config.facebook %}
    <a href="{{ config.facebook }}" target="_blank" aria-label="Facebook">...</a>
{% endif %}
{% if config.instagram %}
    <a href="{{ config.instagram }}" target="_blank" aria-label="Instagram">...</a>
{% endif %}
{% if config.linkedin %}
    <a href="{{ config.linkedin }}" target="_blank" aria-label="LinkedIn">...</a>
{% endif %}
```

## Etape 2 : Avec GrapeJS

1. Creer le modele `FaireFestivalConfig`
2. Migration
3. Admin Unfold conditionnel avec widget GrapeJS
4. Modifier les templates pour lire depuis le modele :
   - `home.html` : tagline depuis `ff_config.tagline`
   - `le_faire_festival.html` : contenu depuis `ff_config.page_presentation`
   - `infos_pratiques.html` : FAQ depuis `ff_config.faq`, acces depuis `ff_config.infos_acces`
5. Passer le contexte `ff_config` dans les vues (via `get_context()` ou middleware)
6. Garder le contenu hardcode actuel comme fallback `{% if ff_config.faq %}...{% else %}(contenu actuel){% endif %}`

## Etape 3 : Generalisation (optionnel, si d'autres skins en ont besoin)

Si un pattern se degage (plusieurs skins avec page_presentation + FAQ + horaires),
extraire une classe abstraite `BaseSkinConfig` avec les champs communs.
Ne pas le faire avant d'avoir 2 cas concrets — pas d'abstraction prematuree.

## Decisions prises

1. **Option A** : un modele par skin (pas de modele generique)
2. **Blocs HTML via GrapeJS** pour le contenu editorial (pas de champs atomiques par question FAQ)
3. **Champs atomiques** uniquement pour les donnees courtes (tagline, horaires)
4. **Etape 1 sans GrapeJS** : juste brancher les `config.*` existants
5. **Contenu hardcode = fallback** quand le champ du modele est vide
6. **LinkedIn** : seul nouveau champ sur Configuration (les autres existent deja)

## Fichiers concernes

- `BaseBillet/models.py` : champ `linkedin` sur Configuration + modele `FaireFestivalConfig`
- `Administration/admin_tenant.py` : admin Unfold conditionnel
- `BaseBillet/templates/faire_festival/partials/footer.html` : dynamiser
- `BaseBillet/templates/faire_festival/views/home.html` : tagline, short_description
- `BaseBillet/templates/faire_festival/views/le_faire_festival.html` : page_presentation
- `BaseBillet/templates/faire_festival/views/infos_pratiques.html` : FAQ, acces, horaires
- `BaseBillet/views.py` : passer `ff_config` dans le contexte
