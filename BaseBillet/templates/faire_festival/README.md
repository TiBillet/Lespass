# Thème Faire Festival pour TiBillet

## Description

Ce thème implémente un design **brutaliste** inspiré de la maquette du Faire Festival, avec une identité visuelle jaune/bleu électrique.

## Architecture des fichiers

```
faire_festival/
├── base.html                      # Template parent avec <head> complet
├── headless.html                  # Template pour requêtes HTMX (sans <head>)
├── partials/
│   └── navbar.html                # Navigation header
├── views/
│   ├── home.html                  # Page d'accueil
│   ├── event/
│   │   ├── list.html              # Liste des événements
│   │   └── retrieve.html          # Détail d'un événement
│   └── membership/
│       └── list.html              # Liste des adhésions/billets
└── README.md                      # Cette documentation
```

## Fichiers statiques

```
static/faire_festival/
└── css/
    └── faire_festival.css         # Styles CSS du thème
```

## Activation du thème

### 1. Exécuter les migrations

Le champ `skin` a été ajouté au modèle `Configuration`. Exécutez :

```bash
python manage.py makemigrations
python manage.py migrate
```

### 2. Activer le thème dans l'administration Django

1. Connectez-vous à l'admin Django : `/admin/`
2. Allez dans **Configuration**
3. Dans le champ **"Thème graphique du site"**, sélectionnez **"Faire Festival (thème brutaliste)"**
4. Sauvegardez

Le site utilisera automatiquement le nouveau thème !

## Fonctionnement du système de skin

### Dans `views.py`

La fonction `get_context()` a été modifiée pour détecter le skin configuré :

```python
# Détermination du skin à utiliser
skin_template_dir = config.skin if hasattr(config, 'skin') and config.skin else "reunion"

# Construction du chemin de template
base_template = f"{skin_template_dir}/headless.html" if request.htmx else f"{skin_template_dir}/base.html"
```

### Dans les vues

Chaque vue utilise maintenant un chemin de template dynamique :

```python
# Exemple pour la page d'accueil
config = Configuration.get_solo()
skin_template_dir = config.skin if hasattr(config, 'skin') and config.skin else "reunion"
template_path = f"{skin_template_dir}/views/home.html"
return render(request, template_path, context=template_context)
```

## Variables de contexte disponibles dans les templates

### Depuis `get_context()`

- `config` : Configuration du tenant (organisation, logo, couleurs, etc.)
- `main_nav` : Liste des liens de navigation
- `user` : Utilisateur connecté
- `profile` : Profil utilisateur sérialisé
- `embed` : Indique si le site est embedé dans une iframe
- `url_name` : Nom de l'URL courante (pour mettre en surbrillance le menu actif)

### Spécifiques aux vues

#### Page d'accueil (`home.html`)
- Hérite uniquement de `get_context()`

#### Liste des événements (`event/list.html`)
- `dated_events` : Liste des événements avec dates
- `paginated_info` : Informations de pagination
- `all_tags` : Tous les tags disponibles pour filtrer
- `active_tag` : Tag actuellement sélectionné
- `tags` : Liste des tags filtrés
- `search` : Terme de recherche

#### Détail d'un événement (`event/retrieve.html`)
- `event` : Événement détaillé
- `event_in_this_tenant` : Booléen indiquant si l'événement appartient au tenant
- `event_max_per_user_reached` : Booléen indiquant si la jauge est atteinte
- `product_max_per_user_reached` : Dict des produits dont la limite est atteinte
- `price_max_per_user_reached` : Dict des prix dont la limite est atteinte

#### Liste des adhésions (`membership/list.html`)
- `products` : Liste des produits d'adhésion disponibles
- `federated_tenants` : Liste des autres lieux de la fédération

## Personnalisation CSS

Le fichier `faire_festival.css` contient toutes les classes CSS avec commentaires en français (FALC).

### Variables CSS principales

```css
:root {
    --couleur-jaune-principal: #FFCB05;
    --couleur-bleu-vif: #0055FF;
    --couleur-blanc: #FFFFFF;
    --epaisseur-bordure: 2.5px;
    --police-titre: 'Archivo Black', sans-serif;
    --police-mono: 'Space Mono', monospace;
}
```

### Classes utilitaires

- `.fond-jaune`, `.fond-bleu`, `.fond-blanc` : Couleurs de fond
- `.texte-jaune`, `.texte-bleu`, `.texte-blanc` : Couleurs de texte
- `.bordure-epaisse` : Bordure épaisse (style brutaliste)
- `.ombre-dure`, `.ombre-dure-petite` : Ombres sans flou
- `.police-titre`, `.police-mono` : Polices de caractères

### Composants principaux

- `.bouton-pilule` : Boutons arrondis de la navbar
- `.bouton-action` : Grands boutons CTA carrés
- `.carte-evenement` : Cartes d'événements
- `.image-evenement` : Images avec effet croix (X)
- `.etiquette-categorie` : Tags de catégories

## Compatibilité

- ✅ Bootstrap 5.3.2
- ✅ HTMX (navigation dynamique)
- ✅ Responsive (mobile, tablette, desktop)
- ✅ Compatible avec le thème "reunion" existant (système de fallback)

## Code FALC (Facile À Lire et à Comprendre)

Tout le code est écrit selon les principes FALC :
- ✅ Commentaires détaillés en français
- ✅ Noms de variables explicites
- ✅ Structure claire et logique
- ✅ Documentation complète

## Support et maintenance

Pour toute question ou amélioration :
1. Consultez les commentaires dans les fichiers CSS et HTML
2. Vérifiez la configuration dans l'admin Django
3. Assurez-vous que les migrations ont bien été exécutées

---

**Créé le** : 2026-02-06
**Version** : 1.0
**Auteur** : Claude (Assistant IA)
