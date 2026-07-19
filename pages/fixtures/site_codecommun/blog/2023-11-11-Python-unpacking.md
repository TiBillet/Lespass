---
slug: python-unpacking
title: Python - L’unpacking
authors: jonas
keywords: [ python, dev, unpacking, sam et max ]
tags: [ python, dev, unpacking, sam et max ]
image: /img/blog/python-unboxing.jpg
description: Une fonctionalité typiquement pythonienne qui permet d’augmenter drastiquement la lisibilité des programmes.
draft: false
---


Il y a un blog que j'aimais farfouiller de temps en temps lors de mes débuts en python : Celui de Sam & Max, disparu
aujourd'hui et plus accessible. Je me permets de resortir quelques archives qui m'ont aidé à l'époque, et qui pourront
très probablement vous aider à votre tour.

# L’unpacking


Dans ce premier d'une, je l'espère, longue série d'articles sur python, parlons d'une des 5 choses
obligatoire à apprendre en python d'après feu le bog Sam&Max.

L’unpacking est une fonctionalité typiquement pythonienne qui permet de prendre un itérable (souvent un tuple), et
de mettre ses éléments dans des variables d’une traite.

Cela permet d’augmenter drastiquement la lisibilité des programmes. Et chez Code Commun, on aime tout ce qui peut aider
à rendre nos logiciels libre plus lisible.

![/img/blog/python-unboxing.jpg](/img/blog/python-unboxing.jpg)

<!-- truncate -->

## Le principe de base

Normalement, si vous voulez mettre le contenu d’un tuple dans des variables, vous devez procéder ainsi :

```python
>>> ducks = ('riri', 'fifi', 'loulou')
>>> duck1 = ducks[0]
>>> duck2 = ducks[1]
>>> duck3 = ducks[2]
>>> print(duck1)
'riri'
>>> print(duck2)
'fifi'
>>> print(duck3)
'loulou'
```

L’unpacking, qu’on pourrait traduire par le terme fort moche de “déballage”, dans le sens “ouvrir un colis”, permet de
faire la même chose, bien plus facilement :

```python
>>> duck1, duck2, duck3 = ducks
>>> print(duck1)
'riri'
>>> print(duck2)
'fifi'
>>> print(duck3)
'loulou'
```

Il n’y a rien à faire, c’est automatique. La seule condition est que le nombre de variables à gauche du signe égal soit
le même que le nombre d’éléments dans la collection de droite.

D’ailleurs, ça marche même avec un seul élément :

```python
>>> ducks = ('riri',)
>>> duck1, = ducks # notez la virgule
>>> duck1
'riri'
```

Et ça marche avec n’importe quel itérable, pas uniquement les tuples. Avec une liste, une string, un générateur…

```python
>>> a, b, c, d = [1, 2, 3, 4]
>>> c
3
>>> a, b = "12"
>>> b
'2'
>>> def yolo():
    yield "leroy"
    yield "jenkins"
...
>>> nom, prenom = yolo()
>>> nom
'leroy'
>>> prenom
'jenkins'
```

Ça marche bien entendu avec un dico ou un set, mais comme ils ne sont pas ordonnés, c’est pas très utile.

## Astuces autour de l’unpacking

On peut utiliser l’unpacking dans des endroits inattendus. Par exemple, pour échanger la valeur de deux variables :

```python
>>> a = 1
>>> b = 2
>>> a, b = (b, a)
>>> a
2
>>> a, b = b, a # les parenthèses sont facultatives dans les tuples
>>> b
2
```

Puisqu’on est dans les tuples sans parenthèses, on peut retourner un tuple et donner l’illusion de retourner plusieurs variables :

```python
>>> def duckmebaby():
...     return "rifi", 'filou', 'louri'
...
>>> et, hop, la = duckmebaby()
>>> et
'rifi'
>>> hop
'filou'
>>> la
'louri'
```

## Allons plus loin.

On peut utiliser l’unpacking à l’intérieur d’une boucle for. Souvenez vous que les itérables peuvent contenir d’autres itérables. Par exemple, j’ai une liste qui contient 3 tuples, chaque tuple contient deux éléments :

```python
>>> scores = [('Monique', '3'), ('David', 10), ('Dick', 1)]
>>> for score in scores:
...     print(score)
...
('Monique', '3')
('David', 10)
('Dick', 1)
```

Si je veux afficher le nom et le score l’un en dessous de l’autre :

```python
>>> for nom_et_score in scores:
...     print(nom_et_score[0])
...     print(nom_et_score[1])
...
Monique
3
David
10
Dick
1
```

Je peux appliquer l’unpacking dans la boucle pour rendre cette opération plus élégante :

```python
>>> for nom, score in scores:
...     print(nom)
...     print(score)
...
Monique
3
David
10
Dick
1
```

Cela marche avec des itérables plus gros, bien entendu. C’est aussi particulièrement utile avec des dictionnaires car on peut les transformer en itérable de tuples :

```python
>>> scores = {'Monique': '3', 'David': 10, 'Dick': 1}
>>> scores['Monique']
'3'
>>> scores.items() # transformation !
dict_items([('Monique', '3'), ('David', 10), ('Dick', 1)])
>>> for nom, score in scores.items():
...     print(nom)
...     print(score)
...
Monique
3
David
10
Dick
1
```

Tout aussi utile, mais plus compliqué, est l’usage de l’unpacking dans l’appel de fonction. Pour cela, on utilise l’opérateur splat, l’étoile en Python.

Soit une fonction qui additionne des nombres :

```python
>> def add(a, b, c):
...     return a + b + c
...
>>> add(1, 2, 3)
6
```

Oui, imaginons que je suis complètement débile, et que j’ai cette fonction pérave dans mon code. Vous noterez dans les articles que je l’utilise souvent sur le blog. C’est la fonction fourre tout pour expliquer un truc quand j’ai pas d’idée.

Maintenant, imaginez que je veuille additionner des canards. Si, ça marche en Python :

```python
>>> 'riri' + 'fifi' + 'loulou' # what the duck ?
'rirififiloulou'
```

Maintenant je me refais mon tuples de canards :

```python
>>> # nous entrerons dans la bande à picsou, youhou
>>> duckyou = ('riri', 'fifi', 'loulou')
```

Si je veux utiliser ma fonction pourrie pour mon use case stupide, je ferai ceci :

```python
>>> add(duckyou[0], duckyou[1], duckyou[2])
'rirififiloulou'
```

Voilà une perte de productivité intolérable, c’est pas comme ça qu’on va faire fructifier son sou fétiche.

On peut forcer l’unpacking avec l’étoile :

```python
>>> add(*duckyou)
'rirififiloulou'
```

Si on oublie l’étoile, le premier paramètre reçoit tout le tuple, et les autres paramètres rien :

```python
>>> add(duckyou)
Traceback (most recent call last):
  File "", line 1, in 
    add(1)
TypeError: add() missing 2 required positional arguments: 'b' and 'c'
```

Les fonctions ont même le droit à un bonus car on peut unpacker des dictionnaires en utilisant la double étoile. Ca ne marche qu’avec les fonctions, et ça va déballer le dico pour que chaque paire clé/valeur soit passée comme nom et valeur de l’argument :

```python
>>> def pas_add(arg1, arg2):
    print(arg1)
    print(arg2)
...
>>> pas_add(arg1="Je suis la valeur 1", arg2="Je m'en branle de qui tu es")
Je suis la valeur 1
Je m'en branle de qui tu es
>>> dicocorico = {'arg1': 'cotcot', 'arg2': 'ouai je pête un cable, l\'avion me soule'}
>>> pas_add(**dicocorico)
cotcot
ouai je pête un cable, l'avion me soule
```

Quand on unpacke des paramètres, il faut s’assurer que le nombre d’arguments passé n’est pas supérieur à ceux existant, sinon ça plante :

```python
>>> dicocorico = {'arg1': 'cocot', 'arg2': 'ouai je pête un cable, l\'avion me soule', 'dang': 'je suis en trop et ça fait chier tout le monde'}
>>> pas_add(**dicocorico)
Traceback (most recent call last):
  File "", line 1, in 
    pas_add(**dicocorico)
TypeError: pas_add() got an unexpected keyword argument 'dang'
>>> stuplet = (1, 2, 3)
>>> pas_add(*stuplet)
Traceback (most recent call last):
  File "", line 1, in 
    pas_add(*stuplet)
TypeError: pas_add() takes 2 positional arguments but 3 were given
```

Par contre, rien ne vous empêche de fournir moins d’arguments et de remplir les autres à la main :

```python
>>> def encore_add(a, b, c, d):
    return a + b + 0 + c + d # je feinte
...
>>> encore_add(10, *stuplet)
16
```

Et on peut bien entendu faire le mega mix. Par exemple, prenons la fonction print, dont la signature accepte une infinité d’arguments positionnels et quelques arguments nommés :

```python
print(value, ..., sep=' ', end='\n', file=sys.stdout, flush=False)
```

Aller, on va lui unpacker sa mère :

```python
>>> ducks = ['riri', 'fifi', 'loulou'] # is this duck typing ?
>>> keywords = {'sep': ' / ', "end": " : vous êtes du coin ? \n"}
>>> print('picsou', *ducks, **keywords)
picsou / riri / fifi / loulou : vous êtes du coin ?
```

Ça c’est fait.

## Python 3, c’est du chocolat

En Python 3, l’unpacking a été amélioré, et on peut maintenant faire de l’unpacking partiel :

```python
>>> # exemple 100% repompé d'un autre article du blog. Duck it.
>>> l = list(range(5))
>>> l
[0, 1, 2, 3, 4]
>>> a, *b = l
>>> a
0
>>> b
[1, 2, 3, 4]
>>> a, *b, c = l
>>> a
0
>>> b
[1, 2, 3]
>>> c
4
```

Ce qui peut être très pratique sur les longs itérables. Comment obtenir la dernière ligne d’un fichier ?

```python
>>> *contenu, dernire_ligne = open('/etc/fstab')
>>> dernire_ligne
'UUID=0e8c3132-8fa2-46d5-a541-2890db9b371f none            swap    sw              0       0\n'
```

Ou alors, dans une boucle :

```python
>>> for initiale, *reste in ducks:
    print(initiale)
...
r
f
l
```