---
slug: howl
title: HOWL - Hypermedia partout
authors: [ jonas ]
description: Sobriété, simplicité dans notre code de développement. HOWL ! ne succombez pas à la pression des javascripties. Soyez libre de choisir la technologie qui correspond le mieux à vos goûts.
tags: [ blog, hypermedia, hyperscript, htmx, sobriété, simplicité, javascript, ]
keywords: [ blog, hypermedia, hyperscript, htmx, sobriété, simplicité, javascript, ]
image: /img/blog/hypermedia/original.png
draft: false
---

### TLDR :

Libérez vous de la pression qu'apporte le Javascript partout. Lorsque vous utilisez une approche hypermédia pour votre
application web, vous êtes libre de choisir la technologie côté serveur qui correspond le mieux à votre problème et à
vos goûts techniques.

![/img/blog/hypermedia/whowillwin.png](/img/blog/hypermedia/whowillwin.png)

<!-- truncate -->

## Préalable.

Nous souhaitons à travers ce blog partager des articles, des tips, des philosophies ou des idées qui ont un rapport de
près ou de loin avec les projets de la coopérative.

Je vais donc commencer par un concept que je découvre récemment (depuis un an ou deux.) et dont j'aime discuter : la "
pile HOWL".

HOWL est l'acronyme de Hypermedia On Whatever you'd Like.

La suite est une traduction de l'article
de [Carson Gross](https://hypermedia.systems/) : [HOWL: Hypermedia On Whatever You'd Like](https://htmx.org/essays/hypermedia-on-whatever-youd-like/)

Si le sujet vous intéresse, je vous invite vous balader sur les sites suivant, il y a plein de concepts intéressants à
découvrir.

- https://hypermedia.systems/
- https://htmx.org/essays/
- https://hyperscript.org/

:::note
SPA : Single Page Application. Une application web qui ne charge qu'une seule page HTML et qui utilise JavaScript pour
modifier le contenu de la page.
Globalement, la philosophie de React, Vue et de tout les frameworks front-end Javascript modernes.

MPA : Multiple Page Application.
:::

## Hypermedia partout

Carson Gross
May 23, 2023

> Le seul grand avantage restant des MPAs est le choix du langage de programmation côté serveur.
> Si vous faites déjà partie de la résistance anti-JavaScript, alors rien de ce que je dirai dans le reste de cet exposé
> n'aura d'importance.
> Mais j'y reviendrai plus tard : ce bateau a peut-être coulé...
>
> Rich Harris - [Les SPA ont-ils ruiné le Web](https://youtubetranscript.com/?v=860d8usGC0o&t=440) ?



Un concept dont nous aimons parler est celui de la "pile HOWL". HOWL est l'acronyme de Hypermedia On Whatever you'd
Like.

En résumé, la pile HOWL est la suivante : lorsque vous utilisez une approche hypermédia pour votre application web, vous
êtes libre de choisir la technologie côté serveur qui correspond le mieux à votre problème et à vos goûts techniques.er
server-side technology best fits your problem and your own technical tastes.

## La pression du JavaScript

Si vous décidez d'utiliser un framework SPA pour votre application web, vous aurez naturellement une large base de code
front-end écrite en JavaScript.

Dans ces conditions, la question suivante se posera inévitablement :

    "Pourquoi ne faisons-nous pas aussi le back-end en JavaScript ?"

C'est une question raisonnable et il y a beaucoup d'avantages à adopter le même langage de programmation des deux côtés
du fil :

- Vous pouvez partager la logique d'application entre les deux bases de code. La logique de validation en est un bon
  exemple.
- Vous pouvez partager des structures de données entre les deux bases de code.
- Vous pouvez acquérir une expertise dans un seul langage, JavaScript, ce qui permet aux développeurs de travailler plus
  facilement sur les différentes parties de votre application.
- Vous pouvez réutiliser le système de construction et les connaissances en matière de gestion des dépendances que vous
  avez acquises pour la partie frontale.

Cette pression en faveur de l'adoption de JavaScript ne fera que croître au fur et à mesure que votre investissement
dans l'écosystème JavaScript augmentera.

En outre, JavaScript s'est considérablement amélioré au cours des cinq dernières années et il existe aujourd'hui
plusieurs excellents applications côté serveur pour l'exécuter. Bon nombre des anciens arguments concernant le désordre
du
langage peuvent être écartés car ils peuvent être évités grâce au _linting_, à la discipline des développeurs, etc.

JavaScript est le langage dominant parmi les leaders d'opinion en matière de développement web et il existe un grand
nombre de tutoriels, de _code camps_, etc. qui mettent fortement l'accent sur ce langage. Rien ne réussit mieux que le
succès, et JavaScript (ainsi que React) a réussi.

Appelons le résultat de cette situation la pression JavaScript et reconnaissons que presque tous les développeurs
travaillant dans le web la ressentent au moins dans une certaine mesure.

![/img/blog/hypermedia/htmlvsjson.png](/img/blog/hypermedia/htmlvsjson.png)

## Hypermedia : Notre seul espoir

Quel espoir les développeurs non-JavaScript ont-ils dans le développement web ?

Eh bien, il existe une technologie plus ancienne utilisé dans les navigateurs : l'hypermédia.

Les navigateurs offrent un excellent support HTML (et le Document Object Model, ou DOM). En fait, même si vous utilisez
un framework SPA, vous travaillerez avec cette infrastructure hypermédia sous une forme ou une autre (via des modèles
JSX, par exemple), ne serait-ce que pour créer des interfaces utilisateur qu'un navigateur peut comprendre.

Vous utiliserez donc HTML ou les API DOM connexes d'une manière ou d'une autre dans votre application web.

**Et si nous faisions de HTML un hypermédia plus puissant ?**

C'est l'idée de [htmx](https://htmx.org/), qui permet de mettre en œuvre
des [modèles d'application web modernes courants](https://htmx.org/examples) en utilisant l'
approche hypermédia. Cela comble le fossé entre les MPA et les SPA traditionnelles, en rendant possible l'adoption de l'
approche hypermédia pour un nombre beaucoup plus important d'applications web.

Une fois que vous avez adopté cette approche hypermédia (et rappelez-vous que vous allez de toute façon utiliser
l'infrastructure hypermédia, alors pourquoi ne pas l'exploiter autant que possible ?), un effet secondaire surprenant se
produit :

Soudain, l'avantage du choix du langage côté serveur que Harris attribuait aux MPAs est de nouveau d'actualité.

Si l'interface de votre application est principalement écrite en termes de HTML, avec peut-être un peu de script côté
client, et sans grande base de code JavaScript, vous avez soudainement diminué de façon spectaculaire (ou entièrement
éliminé) la pression JavaScript au niveau de l'interface.

Vous pouvez désormais choisir le langage (et le cadre) côté serveur en fonction d'autres considérations : techniques,
esthétiques ou autres :

- Peut-être travaillez-vous dans le domaine de l'IA et souhaitez-vous utiliser une variante Lisp pour votre projet ?
- Peut-être travaillez-vous dans le domaine du big data et souhaitez-vous utiliser Python ?
- Vous connaissez peut-être très bien Django et vous aimez l'approche "batteries-included" qu'il adopte.
- Peut-être préférez-vous Flask et l'approche dépouillée qu'il adopte ?
- Peut-être aimez-vous l'aspect brut et proche du HTML de PHP ?
- Vous avez peut-être une base de code Java existante qui a besoin d'être améliorée.
- Peut-être que vous apprenez Cobol, et que vous voulez utiliser htmx pour en faire une interface agréable.
- Peut-être aimez-vous vraiment Rust, Ocaml, Kotlin, Haskell, .NET, Clojure, Ada, ColdFusion, Ruby... peu importe !

Il s'agit là de points de vue techniques, philosophiques et esthétiques tout à fait raisonnables.

Et, en adoptant l'hypermédia comme principale technologie _front_, vous poursuivez tous ces objectifs sans avoir
recours à une double base de code. L'hypermédia ne se soucie pas de ce que vous utilisez pour le produire : vous
pouvez utiliser l'hypermédia sur ce que vous voulez. HOWL !

## Un Web ouvert à tous

Et quand nous disons "tout le monde", nous le pensons vraiment.

Voici une capture d'écran de la sous-section HOWL du [discord htmx](https://htmx.org/discord) récemment. Notez qu'il ne
s'agit que des canaux qui
ont un trafic actif, il y en a beaucoup d'autres.

![/img/blog/hypermedia/howl-channels.png](/img/blog/hypermedia/howl-channels.png)

Vous pouvez voir que nous avons des conversations en cours dans un tas de langages de programmation et de frameworks
différents : Java, Go, .NET, Rust, Clojure, PHP, Ruby, Python, Ocaml. Nous avons même des gens qui parlent de
l'utilisation de htmx avec Bash et Cobol !

C'est exactement l'avenir que nous voulons voir : un Web riche et dynamique dans lequel chaque langage et cadre
d'arrière-plan peut jouer le rôle d'une alternative intéressante. Chaque langage et framework possède ses propres
forces et propres cultures et chacun peut contribuer au [système hypermédia](https://hypermedia.systems/) magique qu'est
le Web.

## Mais... S'agit-il d'une résistance anti-JavaScript ?

Avant de terminer cet essai, nous voulons aborder l'idée que la résistance à **JavaScript partout** est nécessairement
anti-JavaScript.

Il est vrai que nous avons eu notre [part de blagues sur JavaScript](https://htmx.org/img/js-the-good-parts.jpeg) et que
nous sommes allés jusqu'à créer un langage de script alternatif pour le web, l'hyperscript.

On pourrait donc penser que nous devrions être des anti-javascripteurs patentés.

Mais, au contraire, nous apprécions profondément JavaScript.

Après tout, htmx et hyperscript sont tous deux construits en JavaScript. Nous n'aurions pas pu créer ces bibliothèques
sans JavaScript qui, quoi qu'on en dise, a le grand mérite d'être là.

Nous allons même jusqu'à recommander l'utilisation de JavaScript pour les besoins de scripts frontaux dans une
application hypermédia, à condition que vous scriptiez d'une manière adaptée aux hypermédias.

De plus, nous ne déconseillons pas l'utilisation de JavaScript (ou TypeScript) côté serveur pour une application
hypermédia, si ce langage est la meilleure option pour votre équipe. Comme nous l'avons dit précédemment, JavaScript
dispose aujourd'hui de plusieurs excellents runtimes côté serveur et de nombreuses excellentes bibliothèques côté
serveur.

C'est peut-être la meilleure option pour vous et votre équipe, et il n'y a aucune raison de ne pas l'utiliser.

Hypermedia On **Whatever you'd Like** signifie exactement cela : ce que vous voulez.

Mais JavaScript n'est pas, et ne devrait pas être, la seule option côté serveur pour votre équipe.

## Le grand retournement

Avec la résurgence de l'intérêt pour les hypermédias (et leur amélioration), un avenir ouvert et diversifié pour le Web
est désormais une possibilité réelle, voire une réalité émergente.

Le Web a été conçu pour être un système hypermédia ouvert, polyglotte et participatif.

Et ce rêve n'a pas encore pris fin, du moins pas encore !

Nous pouvons maintenir ce rêve en vie en réapprenant et en adoptant la technologie fondamentale du web : l'hypermédia.


