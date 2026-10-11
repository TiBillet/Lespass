# Volutes Tibillet · guide d'utilisation

Le motif de volutes est la texture de marque de Tibillet. Toutes les valeurs ci-dessous sont celles du document de DA (`da-tibillet`), pas des suppositions.

## Les fichiers

| Fichier | Couleur des volutes | Opacité | Couleur de fond en aplat derrière | Usage réel |
|---|---|---|---|---|
| `tibillet-volutes-blanc.svg` | Blanc `#ffffff` | 0,04 | une des cinq couleurs de marque : Letchi `#e93363`, Zanana `#e9b322`, Chouchou `#259d49`, Loséyan `#4296cc` ou Violet `#8b5fb0` | **la carte** |
| `tibillet-volutes-fond-sable.svg` | Brun-sable `#b2a07f` | 0,04 (intégrée au fichier) | Sable `#f4ede0` | **le fond de page** |

Tous les fichiers ont le même format : SVG vectoriel, viewBox de référence 1920 × 4000, net à n'importe quelle taille de destination. On garde le fichier tel quel quel que soit l'écran ou le support.

Chaque SVG ne peint que les volutes : entre elles, le fichier est vide (transparent). C'est la couleur posée **derrière** (ou l'aplat sur lequel on pose) qui remplit le reste.

## Les deux usages réels

Il y a deux façons dont le motif apparaît dans le produit, et elles n'utilisent pas les mêmes fichiers.

### Usage A · La carte (volute blanche sur aplat de couleur)

La **couleur de marque est le fond plein**, et la volute posée dessus est **blanche**, à faible opacité. C'est ce qui fait les cartes Tibillet, déclinables sur les cinq couleurs.

```css
.carte {
  position: relative;
  background: #e93363;              /* la couleur de marque EST le fond (Letchi, Zanana, …) */
  border-radius: 16px;
  overflow: hidden;
  color: #fff;
}
.carte__volute {
  position: absolute;
  inset: 0;
  background: url('tibillet-volutes-blanc.svg') center / cover no-repeat;
  opacity: 0.04;                    /* volute blanche discrète */
  pointer-events: none;
}
.carte > *:not(.carte__volute) { position: relative; z-index: 1; }
```

Pour changer de couleur de carte, on change `background` (une des cinq couleurs de charte). La volute reste le même fichier blanc.

### Usage B · Le fond de page (ton sur ton)

Volutes brun-sable à peine devinables, sur le fond Sable. Le fichier `fond-sable` a déjà son opacité intégrée (0,04), donc rien à régler.

```css
body {
  background-color: #f4ede0;                               /* Sable */
  background-image: url('tibillet-volutes-fond-sable.svg');
  background-repeat: repeat-y;
  background-size: 100% auto;      /* le motif grandit avec la largeur de l'écran */
  background-position: center top;
}
```

Le motif défile avec la page et son échelle suit la largeur de l'écran.

**Mode sombre** : même principe, le doc utilise un fond `#141116` avec les mêmes volutes brun-sable à 0,06 d'opacité. Pour l'obtenir, ouvrir `fond-sable`, passer le `rect` de fond à `#141116` et l'`opacity` du groupe à `0.06`.

## La règle d'imbrication des fonds

Quand un fond est en volutes, ce qui se pose dessus suit toujours le même ordre, sur trois niveaux :

1. **Le fond de page** : volutes brun-sable `#b2a07f` à 0,04, sur Sable `#f4ede0`.
2. **Le premier bloc posé dessus** : fond Papier `#faf8f5`, **jamais de volutes**. Il masque le fond de page.
3. **Une carte à l'intérieur** : aplat d'une des cinq couleurs de charte, avec la **volute blanche** par-dessus (usage A).

Donc : le fond de page porte le ton sur ton, les blocs de contenu masquent, et seules les cartes reprennent le motif, en blanc sur couleur.

## Régler l'opacité

- **Volute blanche (carte)** : via `opacity` sur l'élément qui la porte en CSS, à `0.04`.
- **Fond-sable** : l'opacité (0,04) est écrite dans le fichier. Pour la changer, ouvrir le SVG et modifier l'attribut `opacity` du premier `<g>`, juste après `<svg>` :

```xml
<g opacity="0.04">   <!-- 0.05, 0.03, etc. -->
```

## Changer une couleur dans un fichier

Chaque volute est colorée par un attribut `fill` (présent deux fois, une par tuile). Pour recolorer, ouvrir le SVG et remplacer la valeur :

```xml
<g transform="…" fill="#ffffff">   <!-- la couleur du motif -->
```

## Les couleurs de la charte

| Nom | Hex |
|---|---|
| Letchi | `#e93363` |
| Zanana | `#e9b322` |
| Chouchou | `#259d49` |
| Loséyan | `#4296cc` |
| Violet | `#8b5fb0` |
| Sable | `#f4ede0` |
| Papier | `#faf8f5` |

## À faire / à éviter

**À faire**
- Carte : couleur de marque en fond plein, volute **blanche** par-dessus à 0,04.
- Fond de page : `fond-sable` sur Sable `#f4ede0`, laissé à 0,04.
- Laisser les blocs de contenu masquer le fond de page (ils sont en Papier, sans volutes).
- Garder les SVG tels quels : ils s'adaptent à toutes les tailles.

**À éviter**
- Mettre des volutes sur un bloc de premier niveau : il masque le fond, il ne le porte pas.
- Monter l'opacité du fond de page au point d'en faire un décor (effet « papier peint »).
- Convertir en PNG/JPG pour le web : on perd la netteté et le poids grimpe. Le SVG pèse 18 Ko et reste net partout.
