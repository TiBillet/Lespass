---
slug: python-comprehension-list
title: Python - Comprehension Lists
authors: jonas
keywords: [ python, dev, compli, comprehension list, listes en intention, sam et max ]
tags: [ python, dev, compli, comprehension list, listes en intention, sam et max ]
image: /img/blog/python-gen.jpg
description: Dans le top 10 des raisons d’aimer Python se hisse aisément les listes en intension, ou “comprehension lists”. Rappel du concept, et un petit tour complet de ce qu’on peut en faire.
draft: false
---

![/img/blog/python-gen.jpg](/img/blog/python-gen.jpg)

# Python - Comprehension Lists

Dans le top 10 des raisons d’aimer Python se hisse aisément les listes en intension, ou “comprehension lists” pour les
gens branchés.

Rappel du concept, et un petit tour complet de ce qu’on peut en faire. Les connaisseurs attendront le
second article qui aborde des notions avancées, et contiendra quelques bonus.

On continue de ressusiter les articles de Sam et Max tout en se formant ? C'est parti !

<!-- truncate -->

## La boucle for

Disclaimer: pour comprendre ce petit gros article, il faut être à l’aise avec la boucle for et les listes.

En Python, on itère beaucoup, c’est à dire qu’on applique très souvent un traitement à tous les éléments d’une séquence,
un par un. Et pour ça il y a la boucle for:

```python
sequence = ["a", "b", "c"]
for element in sequence:
    print(element)
# a
# b
# c
```

Et très souvent, on fait une nouvelle liste avec les éléments de la première liste, mais modifiés:

```python
sequence = ["a", "b", "c"]
new_sequence = []
for element in sequence:
    new_sequence.append(element.upper())

print(new_sequence)
# ['A', 'B', 'C']
```

## Les listes en intension: la base

Cette opération – prendre une séquence, modifier les éléments un par un, et faire une autre liste avec – est très
commune. Et comme pour à peu près tout ce qui est opération courante, Python possède une manière élégante de le faire
plus vite.

Reliez bien le bloc précédent, il devient:

```python
sequence = ["a", "b", "c"]
new_sequence = [element.upper() for element in sequence]
print(new_sequence)
# ['A', 'B', 'C']
```

Il n’y a aucun mystère, ce code fait exactement la même chose, mais:

```python
new_sequence = []
for element in sequence:
    new_sequence.append(element.upper())
```

Est réduit à:

```python
new_sequence = [element.upper() for element in sequence]
```

Ne cherchez pas un truc compliqué, c’est juste une question de syntaxe, ça fait la même chose, mais écrit différemment :
à droite, la boucle, à gauche, ce que l’on veut mettre dans la liste finale.

Et c’est surtout beaucoup plus court.

Là où ça devient franchement sympa, c’est que l’on peut assigner le résultat d’une liste en intension directement à la
variable originale:

```python
sequence = ["a", "b", "c"]
new_sequence = [element.upper() for element in sequence]
print(new_sequence)
# ['A', 'B', 'C']
```

Devient alors:

```python
sequence = ["a", "b", "c"]
sequence = [element.upper() for element in sequence]
print(sequence)
# ['A', 'B', 'C']
```

Et vous avez du coup un moyen très propre de transformer toute une liste.
Listes en intension avancées

On peut faire bien plus avec les listes en intension. Python est un langage dynamiquement typé, donc on peut transformer
carrément le type de liste.

```python
sequence = [1, 2, 3]
print([str(nombre) for nombre in sequence])
# ['1', '2', '3']
```

On peut aussi faire des opérations un peu plus complexes:

```python
sequence = [1, 2, 3]
print(['a' * nombre for nombre in sequence])
# ['a', 'aa', 'aaa']
```

Et même construire des sequences imbriquées à la volée:

```python
sequence = [1, 2, 3]
print(list(range(5)))  # petit rappel de l'usage de la fonction range
# [0, 1, 2, 3, 4]

sequence = [(nombre, list(range(nombre))) for nombre in sequence]
print(sequence)
# [(1, [0]), (2, [0, 1]), (3, [0, 1, 2])]

print(sequence[-1])
# (3, [0, 1, 2])

print(sequence[-1][0])
# 3

print(sequence[-1][1])
# [0, 1, 2]
```

La syntaxe `[expression for element in sequence]` autorise n’importe quelle expression, du coup on peut créer des listes
très élaborées, en utilisant tous les opérateurs mathématiques, logiques, etc, et toutes les fonctions que l’on veut.
Filtrer avec les listes en intension

Une autre opération courante consiste à filtrer la liste plutôt que de la transformer :

```python
nombres = range(10)
nombres_pairs = []
for nombre in nombres:
    if nombre % 2 == 0:  # garder uniquement les nombres pairs
        nombres_pairs.append(nombre)

print(nombres)
# [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

print(nombres_pairs)
# [0, 2, 4, 6, 8]
```

Évidement Python a également une syntaxe plus courte pour cela. Il suffit de rajouter la condition à la fin:

```python
nombres = range(10)
print([nombre for nombre in nombres if nombre % 2 == 0])
# [0, 2, 4, 6, 8]
```

Toutes les expressions habituellement utilisables pour tester une condition sont également disponibles.

Bien sûr, rien ne vous empêche de filtrer ET de transformer la liste en même temps. En clair, un nouvel arrivant à
Python fera ça:

```python
nombres = range(10)
sommes = []
for nombre in nombres:
    if nombre % 2 == 0:
        somme = 0
        for i in range(nombre):
            somme += i
        sommes.append(somme)

print(sommes)
# [0, 1, 6, 15, 28]
```

Un codeur qui trouve ses marques fera ça:

```python
sommes = []
for nombre in range(10):
    if nombre % 2 == 0:
        sommes.append(sum(range(nombre)))

print(sommes)
# [0, 1, 6, 15, 28]
```

Un pythoniste affranchi ira droit au but:

```python
print([sum(range(nombre)) for nombre in range(10) if nombre % 2 == 0])
```

Bon, en vérité il fera plutôt:

```python
[sum(range(nombre)) for nombre in range(0, 10, 2)]
```

Mais c’était pour l’exemple :-)

Les listes en intension ont encore plus à offrir, la suite au prochain article !