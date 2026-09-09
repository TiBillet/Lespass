# Piège potentiellement récurrent sur laboutik

--- 

## Dataset
Sur laboutik, on utilise des data-* pour passer des données du django qui rend les templates avec le context, au JS.

Dans le js il y avait un check sur `dataset.stockBloquant` (`data-stockBloquant` en HTML), le problème étant, les majuscules sont interdits dans les attributs de dataset. Donc le vrai rendu HTML était `data-stockbloquant` ce que le JS n'arrivait donc pas à lire...

Donc il faut toujours écrire les data-* en snake_case (minuscules, mots séparés par des `_`)
