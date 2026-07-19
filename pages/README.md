# Construire le site de votre lieu

Ce guide s'adresse aux personnes qui **écrivent** le site : pas besoin de savoir
coder. Il décrit le constructeur de pages de TiBillet, accessible dans
l'administration sous **« Site web personnalisé »**.

> Le module doit être activé pour votre lieu. S'il n'apparaît pas dans le menu,
> activez-le depuis le **tableau de bord** : chaque module y a sa carte, avec un
> interrupteur.

---

## 1. L'idée en une phrase

Une **page** est une pile de **blocs**, empilés de haut en bas.

Vous n'écrivez pas une page en une seule fois : vous ajoutez des blocs les uns
sous les autres, chacun avec son rôle — un titre d'ouverture, un paragraphe, une
galerie, une carte, une FAQ. Vous les réordonnez en les faisant glisser.

```
Page « Accueil »
├── Bloc 1  Section / Bannière d'ouverture     ← le grand titre
├── Bloc 2  Texte                              ← un paragraphe
├── Bloc 3  Images / Photo pleine largeur
└── Bloc 4  Section / Appel à l'action         ← deux boutons
```

---

## 2. Prise en main : votre première page

1. **Site web personnalisé → Pages → +** (bouton en haut à droite).
2. Donnez un **titre**. L'**adresse (slug)** se remplit toute seule — c'est ce
   qui apparaîtra dans l'URL : `Nos ateliers` → `/nos-ateliers/`.
3. **Enregistrer**.
   > Quelques adresses sont réservées au fonctionnement du site (`admin`, `api`,
   > `event`, `memberships`, `connexion`, `media`…). Si vous en choisissez une,
   > l'enregistrement est refusé avec un message : changez simplement l'adresse.
4. Ouvrez l'onglet **« Blocs »** : c'est là que vit le contenu.
5. **Ajouter un bloc** → choisissez son **type** → **Enregistrer**.
6. Cliquez sur **« ✎ modifier »** sur la ligne du bloc pour saisir son contenu.
7. Quand tout vous convient, cochez **Publiée** et cliquez sur **« ↗ ouvrir »**
   pour voir le résultat.

> **Tant que « Publiée » est décochée**, la page est un brouillon : invisible du
> public. Vous pouvez donc la préparer tranquillement.
>
> Pour la relire avant publication : restez connecté·e à l'administration et
> tapez son adresse à la main dans le navigateur (`/nos-ateliers/`). Le lien
> « ↗ ouvrir » de la liste, lui, n'apparaît qu'une fois la page publiée.

### Pourquoi deux étapes pour créer un bloc ?

L'onglet « Blocs » est un **sommaire** : il montre le type et le titre de chaque
bloc, et sert à les réordonner. Le contenu détaillé se saisit dans la fiche du
bloc, parce que les champs à remplir **dépendent du type choisi** — une citation
ne demande pas les mêmes informations qu'une carte GPS.

---

## 3. La liste des pages

Elle n'affiche que les **pages principales** — celles qui ne sont rangées sous
aucune autre. Le compteur en haut le rappelle : « 6 résultats (32 résultats) ».

| Élément | À quoi ça sert |
|---|---|
| **⠿** (poignée) | Glissez-déposez pour changer l'ordre dans le menu du site |
| **›** (chevron) | Déplie les blocs de la page et ses sous-pages |
| **Publiée** | Interrupteur : basculez-le et cliquez sur « Enregistrer » en bas |
| **Accueil** | Signale la page servie à la racine du site |
| **Blocs / Sous-pages** | Compteurs, pour repérer une page vide d'un coup d'œil |
| **↗ ouvrir** | Ouvre la page publique dans un nouvel onglet |

Pour voir les sous-pages dans la liste, utilisez **Filtres → Niveau**.

---

## 4. Les sept types de blocs

Le catalogue est organisé **par intention**, pas par apparence. Demandez-vous
« qu'est-ce que je veux dire ? », le type suit. Ensuite, l'**affichage** décide
de la forme.

### Texte
Un article, un paragraphe. S'écrit en **Markdown** (voir §6).
→ *Titre, Texte*

### Section — « je mets quelque chose en avant »
Le type le plus polyvalent. Huit affichages :

| Affichage | Pour quoi | Ce qu'on remplit |
|---|---|---|
| **Bannière d'ouverture** | Le grand titre en haut d'une page | Titre, sous-titre |
| **Texte avec image à gauche / à droite** | Présenter en alternant texte et visuel | Titre, texte, image, un bouton |
| **Texte avec vidéo** | Idem avec une vidéo déposée | Titre, texte, vidéo |
| **Média + texte + sous-cartes** | Une section composée, riche | Titre, texte, image, vidéo, sous-cartes |
| **Carte** | Se range automatiquement en grille avec les cartes voisines | Titre, sous-titre (affiché au-dessus du titre), badge, texte, image, un bouton |
| **Appel à l'action** | Inviter à adhérer, réserver, contacter | Titre, sous-titre, texte, deux boutons |
| **Citation** | Un témoignage signé | Texte, nom, rôle, photo de l'auteur |

> **L'image de fond de la bannière** n'est pas réglable dans le bloc : c'est
> l'image générale du lieu (**Configuration → Image de fond**), pour qu'elle
> reste cohérente partout.

> **Les cartes se regroupent toutes seules.** Posez trois blocs « Carte » à la
> suite : ils s'affichent côte à côte. Il n'y a pas de bloc « grille » à créer.

### Images
C'est l'**affichage** qui décide d'où viennent les fichiers :

| Affichage | Les images viennent de |
|---|---|
| **Photo pleine largeur** | le champ **Image** du bloc |
| **Vignette centrée** | le champ **Image** du bloc |
| **Galerie en grille** | l'encart **« Images de galerie »** en bas de la fiche |
| **Bande de logos cliquables** | l'encart **« Images de galerie »** en bas de la fiche |

L'encart « Images de galerie » n'apparaît que pour les deux derniers — inutile d'y déposer
des fichiers pour les deux premiers, ils ne seraient pas affichés.

> **Taille maximale : 10 Mo par image.** Cette limite vaut pour toutes les images
> du site — celles des blocs comme l'image de partage d'une page. Une photo sortie
> d'un appareil reflex la dépasse souvent : réduisez-la avant de l'envoyer.

### Contenu intégré
Du contenu qui vient d'ailleurs, donc toujours une adresse web.

| Affichage | Pour quoi |
|---|---|
| **Vidéo en ligne** | YouTube, Vimeo, PeerTube |
| **Formulaire ou widget** | Un service externe (+ une hauteur en pixels) |
| **Inscription newsletter** | Formulaire Ghost |

> Le choix n'est pas cosmétique : chaque affichage applique ses propres **règles
> de sécurité**. Pour un widget, l'hôte doit être autorisé par l'administration
> racine (**Configuration racine → Domaines d'intégration autorisés (iframe)**) — sans quoi rien
> ne s'affiche.

### Lieu
La carte des points GPS **et** les infos pratiques à côté, dans **un seul bloc**.
Les deux moitiés forment un ensemble à l'écran.

- **Colonne de gauche** : le champ *Contenu structuré*. Recopiez l'exemple
  ci-dessous et remplacez seulement les textes. Types d'éléments disponibles : `badge`, `para`, `horaire`, `adresse`,
  `accessibilite`, `transport`.
  ```json
  [
    {"type": "badge", "texte": "Nous trouver"},
    {"type": "horaire", "texte": "MARDI → SAMEDI 10h → 19h"},
    {"type": "adresse", "texte": "La Cité\n55 avenue Louis Breguet\n31400 Toulouse"},
    {"type": "transport", "titre": "BUS", "lignes": ["Ligne 37 — arrêt Bréguet"]}
  ]
  ```
- **Colonne de droite** : le *Badge* (bandeau d'adresse) et les *Points GPS*.
  ```json
  [{"lat": 43.5568, "lng": 1.4835, "label": "La Cité"}]
  ```

> Ne coupez pas ce bloc en deux (les infos d'un côté, la carte de l'autre) :
> vous obtiendriez deux sections à moitié vides.

### Question / réponse
Un bloc = **une** question. Posez-en plusieurs à la suite : elles s'affichent en
accordéon, sur deux colonnes.
→ *Titre = la question, Texte = la réponse*

### Liste automatique
Se remplit tout seul, et reste à jour sans que vous y touchiez.

| Source | Affiche |
|---|---|
| **Les sous-pages d'une page** | Les pages rangées sous celle-ci, en cartes |
| **Les prochains évènements** | L'agenda du lieu |

*Nombre d'éléments* limite la longueur de la liste. Pour les sous-pages, *Page à lister*
permet de pointer une **autre** page que celle où se trouve le bloc (vide = la
page courante).

---

## 5. Organiser plusieurs pages

### Ranger une page sous une autre
Dans la fiche d'une page, le champ **Page parente** la range sous une autre. Vous
obtenez un arbre — jusqu'à **6 niveaux**.

Ranger une page apporte automatiquement deux choses :

- un **fil d'Ariane** en haut (`Accueil › Présentation › Charte et valeurs`) ;
- la possibilité de la lister avec un bloc *Liste automatique*.

Les liens **précédent / suivant** en bas de page, eux, n'apparaissent que si la
rubrique est en **Menu latéral** (voir ci-dessous).

### Choisir où la page apparaît : le champ « Place dans la navigation »

| Valeur | Effet |
|---|---|
| **Barre de navigation** | Dans le menu du haut. Ses sous-pages forment un menu déroulant |
| **Menu latéral (documentation)** | Un menu se déplie dans la marge gauche, avec tout l'arbre de la rubrique. Sur mobile, il se replie en bouton |
| **Hors navigation** | La page existe et reste accessible, mais n'apparaît dans aucun menu |

Le **menu latéral** convient aux rubriques à plusieurs articles — une
documentation, un journal, un dossier. Le réglage se pose sur la **page
principale** de la rubrique : ses sous-pages en héritent, et c'est lui qui fait
apparaître les liens *précédent / suivant* en bas de chaque article.

*Hors navigation* est utile pour une page qu'on ne veut atteindre que par un
lien : une page ne figurant que dans un bloc *Liste automatique*, une page de
remerciement après un formulaire.

### La page d'accueil
Cochez **Page d'accueil** : cette page est servie à la racine du site (`/`).
Une seule à la fois, et elle ne peut pas être rangée sous une autre.

### Changer l'allure générale du site

**Site web personnalisé → Configuration du site** permet de choisir le **thème
graphique** (couleurs, polices, mise en page). Il s'applique à tout le site :
vos pages n'ont pas à s'en occuper.

---

## 6. Écrire en Markdown

Le bloc **Texte** s'écrit en Markdown, une manière d'écrire du texte mis en forme
sans quitter le clavier. L'éditeur affiche une barre d'outils et un aperçu (l'œil).

```markdown
## Un titre de section
### Un sous-titre

Du texte avec du **gras**, de l'*italique* et un [lien](https://exemple.org).

- une liste
- à puces

> Une citation.

Deux espaces en fin de ligne  
forcent un retour à la ligne.
```

### Insérer une image dans un article

1. Déposez vos images dans l'encart **« Images de galerie »**, en bas de la fiche du bloc
   (visible après le premier enregistrement).
2. Insérez-les dans le texte en indiquant **leur position** dans l'encart :

```markdown
![Légende de la photo](galerie:1)
```

`galerie:1` = la première image de l'encart, `galerie:2` la deuxième, etc. Le
numéro suit **l'ordre affiché** : si vous réordonnez vos images par
glisser-déposer, pensez à relire vos références.

### Le sommaire

Les titres `##` et `###` de vos articles alimentent **automatiquement** un
encadré « Sommaire » repliable, affiché en haut de la page. Vous n'avez rien à déclarer : structurez
votre texte avec des titres, le sommaire suit.

> Le grand titre de la page est déjà posé : vos titres sont donc **rétrogradés
> d'un niveau** à l'affichage. Écrivez `##` pour une section et `###` pour une
> sous-section, c'est la convention du projet.

### Blocs de code

Trois accents graves, puis le langage :

````markdown
```python
def bonjour():
    print("salut")
```
````

La coloration syntaxique est appliquée automatiquement.

### Ce qui est retiré à l'affichage

Vous pouvez écrire du HTML simple dans un bloc Texte, mais **les attributs
`class` et `style` sont supprimés** au moment de l'affichage, pour des raisons de
sécurité. Écrire `<p style="text-align:center">` ne centrera donc rien.

**La mise en forme appartient au thème du site**, pas au texte que vous saisissez.
Si une présentation vous manque, demandez-la à votre équipe technique : elle sera
ajoutée au thème et s'appliquera partout, de façon cohérente.

---

## 7. Être trouvé sur les moteurs de recherche

La section **« Référencement & partage (SEO) »** de chaque page. Tout est
optionnel — laissé vide, le nécessaire est déduit du titre.

| Champ | Rôle |
|---|---|
| **Titre SEO** | Le titre affiché dans l'onglet et dans Google. Vide = le titre de la page |
| **Méta description** | Le résumé affiché sous le lien dans les résultats. ~150 caractères |
| **Image de partage** | La vignette affichée quand on partage le lien sur les réseaux sociaux |
| **Noindex** | Demande aux moteurs de **ne pas** référencer cette page |

Le fil d'Ariane et les informations de structure sont générés automatiquement
pour les moteurs de recherche.

---

## 8. Questions fréquentes

**Ma page n'apparaît pas sur le site.**
Trois causes, dans l'ordre : « Publiée » est décochée ; « Place dans la navigation »
est sur *Hors navigation* ; le module *Site web personnalisé* est désactivé.

**J'ai déposé une image, elle ne s'affiche pas.**
Vérifiez que l'affichage correspond : *Galerie en grille* et *Bande de logos*
lisent l'encart « Images de galerie », tandis que *Photo pleine largeur* et *Vignette
centrée* lisent le champ **Image** du bloc.

**Je ne trouve pas le champ que je cherche dans un bloc.**
Les champs s'affichent selon le **type** et l'**affichage** choisis : seuls
apparaissent ceux que ce rendu utilise vraiment. Changez l'affichage, les champs
suivent. C'est voulu — cela évite de remplir un champ qui ne s'afficherait nulle
part.

**Mon menu déroulant est trop chargé.**
Passez la rubrique en **Menu latéral (documentation)** : l'arbre se déplie dans
la marge au lieu d'alourdir la barre du haut.

**Je veux supprimer une page, l'administration refuse.**
Deux causes possibles : la page a des **sous-pages** (les supprimer les rendrait
inaccessibles), ou un bloc *Liste automatique* d'une **autre page** la vise dans
son champ *Page à lister*. Défaites le lien d'abord, la suppression passera.

**Puis-je remettre un bloc supprimé ?**
Non. Vérifiez avant de supprimer.

---

## 9. Pour l'équipe technique

- **Catalogue** : `pages/blocs_catalogue.py` est la source unique. `CHAMPS_PAR_TYPE`
  (union par type, utilisée par l'API), `CHAMPS_PAR_AFFICHAGE` (ce que chaque
  gabarit rend vraiment, utilisée par les `conditional_fields` de l'admin),
  `AFFICHAGES_PAR_TYPE`, `AFFICHAGE_PAR_DEFAUT`.
- **Règle non négociable** : jamais un nouveau **type** pour une variation
  purement visuelle — c'est un **affichage**. Un type répond à « qu'est-ce que je
  dis ? », un affichage à « sous quelle forme ? ».
- **Gabarits** : `pages/templates/pages/<skin>/partials/bloc_<type>_<affichage>.html`,
  avec repli sur `bloc_<type>.html` puis sur le skin `classic`.
- **Ajouter un affichage** : l'ajouter à `AFFICHAGES_PAR_TYPE` **et** à
  `CHAMPS_PAR_AFFICHAGE`, puis créer le gabarit. Cinq tests vérifient la
  cohérence de l'ensemble (`tests/pytest/test_pages_api.py`).
- **API v2** : `/api/v2/pages/` et `/api/v2/blocs/`, catalogue exposé sur
  `/api/v2/pages/block-types/`. Voir `api_v2/GUIDELINES.md`.
- **Jeux de démonstration**, tous lancés par `demo_data_v2` après un flush :
  `charger_site_lespass` (tenant lespass, couvre les 20 combinaisons),
  `charger_site_faire_festival` (tenant festival, skin dédié ; `--contenu=demo`
  pour la démo, `--contenu=reel` pour le site du vrai festival),
  `charger_site_codecommun` (tenant la-maison-des-communs, site documentaire).
