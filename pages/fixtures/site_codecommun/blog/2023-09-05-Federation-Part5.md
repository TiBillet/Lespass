---
slug: federation-part5
title: Fédération 5 - FEDOW
authors: jonas
keywords: [cashless, fédération, portefeuille, wallet, openwallet, caisse enregistreuse, tibillet, réunion des tiers-lieux, RTLx, économie sociale et solidaire, ess, coopérative, scic]
tags: [cashless, fédération, portefeuille, wallet, openwallet, caisse enregistreuse, tibillet, réunion des tiers-lieux, RTLx, économie sociale et solidaire, ess, coopérative, scic]
image: /img/federons/fedow_logo.jpg
description: Fédérons TiBillet, cinquième partie. Open wallet, blockchain, économie sociale et solidaire sont dans un bateau.
---

![/img/federons/fedow_logo.jpg](/img/federons/fedow_logo.jpg)

<!-- truncate -->

# TiBillet/FEDOW : **FED**erated and **O**pen **W**allet.

## C'est quoi FEDOW ?

Résumé : 

Outil [FLOSS](https://fr.wikipedia.org/wiki/Free/Libre_Open_Source_Software) de création et de gestion d'un groupement de monnaies locales, complémentaire et citoyenne (MLCC) au sein d'un réseau fédéré. 

S'intégrant aux outils [TiBillet](https://tibillet.org) il permet l'utilisation de portefeuilles dématérialisés dans différents lieux associatifs, coopératifs et/ou commerciaux.

Enfin, Fedow intègre des principes de [monnaie fondantes](https://fr.wikipedia.org/wiki/Monnaie_fondante) dans une chaine de block par preuve d'autorité, transparente, non spéculative et non énergivore.

## Code source et documentation technique publiés sous licence AGPLv3 :

[https://github.com/TiBillet/Fedow](https://github.com/TiBillet/Fedow)

## Manifeste pour l'appropriation d'une économie locale, sociale et solidaire.

### Moteur libre et open-source de gestion de monnaies temps et/ou locale.

Parce qu'une banque peut être un logiciel libre :
Nous n'avons pas besoin de blockchain spéculative, de NFT, DeFi ou Dapp ou de tout autre battage techno-solutionniste.

Tout ce dont nous avons besoin, c'est d'un moteur de création monétaire, de gestion de compte et de transactions.
Le tout sous une gestion fédérée et transparente, pour créer des réseaux de points de vente acceptant des monnaies locales, des monnaies temporelles ou même des monnaies qui ne sont pas des monnaies.

Un outil simple pour créer une petite banque à l'échelle d'un petit ou d'un grand territoire et soutenir une économie locale, sociale et inclusive.

### Pourquoi ?

Chez Code Commun (la coopérative numérique qui développe l'écosystème TiBillet), nous pensons que le logiciel libre couplé à des pratiques de gouvernance ouverte et transparente pour une économie sociale et solidaire sont les conditions d'une société que nous souhaitons voir émerger.

Avec **Fedow**, qui s'inscrit dans l'écosystème **TiBillet**, nous souhaitons permettre à chacun de créer ou rejoindre une fédération de monnaies **locale** ou **temps** et de participer à sa gouvernance.

Nous ne croyons pas aux solutions technologiques promises par le Web3 : Blockchains énergivores, création de valeur sur du vide, bulles spéculatives, marchés d'échanges dérégulés, gourous milliardaires… Autant de promesses populistes d'empuissancements non tenues au service d'une économie ultra-libérale de la rareté et de la spéculation.

Ceci dit, nous ne jetons pas le bébé avec l'eau du bain.

Nous pensons que les entreprises humaines, coopératives et locales peuvent (doivent ?) être soutenues par des outils numériques libres pour construire des structures bancaires locales et coopératives au service d'une économie réelle.

Nous pensons que les technologies de blockchain peuvent aider en garantissant la sécurité, la transparence et la gouvernance partagée : *The code we own is law.*

Nous souhaitons construire **Fedow** dans ce sens : un outil numérique simple et compréhensible par chacun pour une économie **réelle, non spéculative et transparente.**


### L'économie réelle et la blockchain éthique

Imaginons un livre de compte tenu par tous les acteurs d'une coopérative.

Dans ce livre de compte, chaque acteur peut créer sa propre monnaie et peut (ou non) l'échanger à un taux fixe avec les autres monnaies de la coopérative.

Une monnaie fédérée à l'ensemble des acteurs est créée, indexée sur l'euro pour que chaque monnaie puisse s'échanger et servir à l'économie réelle des biens et services.

D'autres type de monnaies non indexée sur l'euro peuvent être créées : Monnaie temps pour s'échanger des services ou valoriser le bénévolat, monnaie "cadeau" pour analyser les stocks offerts, monnaie "ticket resto" pour gérer des repas des invités, et même monnaie "libre" compatibles avec d'autres systèmes comme la June.

Couplés au reste des outils de TiBillet, il est alors possible de créer des points de ventes, des caisses enregistreuses, des rapports de comptabilité légaux et des boutiques en ligne qui acceptent indifféremment les monnaies locales et fédérées du réseau, comme des espèces ou cartes bancaires.

Tout ceci avec du matériel DiY et du software low-tech, en favorisant au maximum le réemploi et le reconditionnement de matériel existant, et en utilisant une preuve d'enjeu comme mécanisme de consensus solide, sécurisé et transparent de validation (cf explications plus bas).


### Financement, pérennisation du projet et lutte contre la spéculation.

Imaginons un mécanisme qui puisse à la fois :

- Inciter de nouveaux acteurs à rejoindre la fédération ou en créer de nouvelles.
- Financer le développement du projet libre et coopératif (Problématique récurrente dans le milieu des logiciels  libres).
- Lutter contre la spéculation et l'accumulation des capitaux pour une économie réelle et non financiarisée.

Une idée a été retenue. Elle a le mérite de résoudre les trois problématiques soulevées et s'inspire fortement de la [monnaie fondante](https://fr.wikipedia.org/wiki/Monnaie_fondante) théorisé par l'économiste [Silvio Gesell](https://fr.wikipedia.org/wiki/Silvio_Gesell).

#### Concepts :

- Tout le matériel nécessaire est produit par la coopérative et distribuée à ses acteurs à prix coutant. (matériel de points de vente, TPE, carte RFID, logiciel comptable, e-boutique, etc... voir [TiBillet](https://tibillet.org))
- Chaque utilisateur dispose d'un portefeuille numérique qui lui permet d'utiliser toutes les monnaies du réseau.
- Chaque lieu de point de vente est un **nœud** du réseau et est considéré comme un point de change.
- Les portefeuilles sont utilisables à vie et sans frais pour les utilisateurs ni pour les **nœuds**.
- Un [demeurage](https://fr.wikipedia.org/wiki/Demeurage_(finance)) est appliqué sur les portefeuilles sous la condition suivante : Si la monnaie n'est pas utilisée sous un certain délai (un an ou plus?) elle fond. **Une partie est prélevée pour être réinjecté dans le réseau coopératif.**

Les principes du demeurage et de la monnaie fondante permettent de favoriser la circulation des capitaux. En intégrant ce mécanisme dans le code de **Fedow**, nous tentons d'inciter la création d'un écosystème redistributif, social et solidaire.

Plus vous encouragez vos utilisateurs à utiliser une monnaie locale, plus vous récolterez une partie de la monnaie fondante issu du **demeurage**.

Ce mécanisme propose une solution incitative à la circulation de monnaie(s) locale(s) qui est une grande problématique de beaucoup de MLCC (monnaies locales citoyennes et complémentaires).


### Je suis un utilisateur lambda, en pratique ça donne quoi ?

- J'adhère et donne de mon temps dans une association de quartier qui utilise TiBillet pour gérer ses adhésions : je reçois une carte de membre et l'association me crédite de la monnaie temps.
- Je peux dépenser cette monnaie temps pour réserver des heures d'utilisation d'un fablab ou d'un espace de travail partagé.
- Je scanne ma carte et je peux la recharger en ligne. Je change des euros contre de la monnaie fédérée.
- Je réserve une place dans un festival partenaire de la coopérative qui utilise le système de cashless et de billetterie de TiBillet.
- J'achète le billet, des boissons et de la nourriture sur place avec cette même carte préalablement rechargée : Le festival reçoit de la monnaie fédérée.
- Le festival peut échanger cette monnaie fédérée contre des euros, ou s'en servir pour payer ses prestataires avec tout le bénéfice d'une [monnaie locale complémentaire et citoyenne "MLCC"](https://monnaie-locale-complementaire-citoyenne.net).
- Il me reste de la monnaie sur ma carte. Je peux la dépenser dans un autre lieu qui utilise TiBillet/Fedow ou la garder pour le prochain festival : Elle est valable à vie.
- Je l'oublie dans un tiroir : Je suis régulièrement rappelé à l'utiliser via les newsletters de la fédération qui font la promotion des évènements associatifs et coopératifs du réseau.
- Si ma carte reste inactive pendant un certain temps, la coopérative récupère une partie du contenu du portefeuille et le réinjecte dans le développement du réseau.
- La coopérative se réunit régulièrement pour faire le point sur la circulation des monnaies et choisir les projets dans lesquels réinvestir l'argent récupéré.


(Exemple possible : 1/3 pour le nœud (organisateur de festival, association...),  1/3 pour un fond commun de soutien aux projets associatifs et coopératifs, 1/3 pour la maintenance et le développement de l'outil.)



### Blockchain bas carbone et mécanisme de confiance : La preuve d'enjeux (PoS) et la preuve d'autorité (PoA) : 

Ou comment répondre à la grande question : *Comment faire pour avoir confiance en un système bancaire décentralisé sur lequel repose de l'argent réel ?*


[ATTENTION DISCLAIMER PARTIE VULGARISATION TECHNIQUE CRYPTO !]

Pour créer un système décentralisé mais sécurisé et fiduciaire, le Bitcoin a proposé la preuve de travail (Proof of Work) : Plus on est nombreux à vérifier, plus il est difficile de falsifier le document comptable car il faut convaincre la majorité pour faire consensus.

Pour encourager le nombre, il est proposé de récompenser les validateurs. Et pour savoir quel validateur va récupérer la récompense, on leur propose une énigme. Celui qui réussit à la résoudre gagne la récompense et valide par la même occasion le bloc de transaction. 

Le reste du groupe vérifie ensuite que ce bloc a bien été validé correctement et tente de résoudre l'énigme suivante. On appelle ça "miner" et cela ne peut se faire qu'à l'aide d'ordinateur très puissants.

Résultat : c'est super sécurisé car beaucoup de monde vérifie chaque transaction. 

Corollaire : c'est très (trop) énergivore au point d'en être insoutenable. (Et ne parlons même pas des mécanismes de rareté et de spéculation qui finissent par achever ce système à nos yeux...)

La preuve d'enjeu (Proof of Stake) a été proposée très vite comme une alternative à la preuve de travail (Proof of Work). Dans un système PoS, il n'y a pas de concept de mineurs, de matériel spécialisé ou de consommation massive d'énergie. 

Pour être un validateur, vous devez prouver que vous avez intérêt à ce que tout le système reste bien valide. Chez *Ethereum*, la deuxième blockchain la plus valorisée, vous devez verrouiller une quantité variable de capital comme preuve d'intérêt et vous êtes récompensé en fonction de cette quantité verrouillée.

Ce système est beaucoup moins énergivore, mais il a tendance à favoriser une oligarchie car n'importe qui peut devenir un nœud : il suffit d'être riche...

Avec Fedow, c'est un peu différent. Il est necéssaire de vérifier votre identité comme celle de vos utilisateurs. La preuve d'enjeu, c'est vous ! 

Cette preuve d'enjeu, c'est la quantité de monnaie fédéré que vous récolterez en installant TiBillet/Fedow. Vous avez intérêt à ce que les comptes soient bien valide car vous en possédez une partie des actifs.

Dans ce système, il n'y a pas de concept de mineurs, de matériel spécialisé ou de consommation massive d'énergie. Tout ce dont vous avez besoin, c'est d'un ordinateur ordinaire sous linux.

Et cet ordinateur, vous l'avez déjà : il héberge votre instance TiBillet. Validez la co-optation ou créez votre réseau Fedow, et votre instance TiBillet devient un nœud  qui valide les transactions de tout le réseau en toute transparence.

La preuve d'enjeu, c'est votre instance liée à votre identité. Plus exactement, ce mécanisme de consensus dérivé du *PoS* est appelé une [preuve d'autorité](https://academy.binance.com/fr/articles/proof-of-authority-explained?hide=stickyBar) (PoA).

En pratique : 

- Créez ou rejoignez le nœud primaire Fedow de votre région ou réseau.
- Une fois votre identité validée, votre instance devient un nœud et vous validez les transactions avec les autres validateurs du réseau fédéré.
- Chaque nœud participant fait de même. Si tout le monde est d'accord, alors la transaction est validée. Tout le monde à une copie du même livre de compte : le réseau est résilient aux pannes, décentralisé, immuable et transparent.
- En contrepartie de votre participation à la sécurisation du livre de compte commun, vous recevrez une partie des frais prélevés lors de la revalorisation de la monnaie fondante (le [demeurage](https://fr.wikipedia.org/wiki/Demeurage_(finance))).


### C'est quoi la différence finalement avec une autre blockchain ?

Contrairement à la majorité des crypto-actifs, il n'y a pas de **blocks** fraîchement créés dans le cadre de la récompense pour les validateurs. La monnaie fédérée est émise dans une économie réelle. 

Cette émission est réalisée par les adhérents et utilisateurs de vos lieux lorsqu'ils échangent de vrais euros pour recharger leur carte cashless de festival ou d'adhésion associative.

La monnaie est bien réelle. Elle n'est pas volatile. Le moteur de l'application et le consensus de validation s'assurent qu'il existe et existera toujours 1€ de disponible en banque pour 1 *token* fédéré.

Nous ne sommes pas une startup. Notre but n'est pas de lever des fonds en crypto-actif ou d'entrer en bourse. Nous ne prélevons pas de pourcentage sur les transactions dans le but de revendre les tokens que nous créons nous même sur un marché spéculatif.

Nous construisons TiBillet/Fedow au sein de tiers-lieux populaires, de coopératives et associations culturelles dans le but de construire des communs.

Nous ne souhaitons pas **un** Fedow pour contrôler un actif financier, mais **des** Fedows pour des mises en réseaux de lieux.

Nous sommes une société coopérative d'intérêt collectif, et nous invitons tous les acteurs de TiBillet à devenir sociétaires pour décider ensemble de l'évolution du projet.

Nous sommes [CodeCommun.Coop](https://codecommun.coop), Venez [discuter](https://discord.gg/ecb5jtP7vY) avec nous !

### Projet construit, financé et testé avec le soutien de :

- [Coopérative Code Commun](https://codecommun.coop)
- [la Réunion des Tiers-lieux](https://www.communecter.org/costum/co/index/slug/LaReunionDesTiersLieux/#welcome)
- [La Raffinerie](https://www.laraffinerie.re/)
- [Communecter](https://www.communecter.org/)
- [Le Bisik](https://bisik.re)
- [Jetbrain](https://www.jetbrains.com/community/opensource/#support) supports non-commercial open source projects.
- Le Manapany Festival
- Le Demeter

## Contact :

- https://discord.gg/ecb5jtP7vY
- https://chat.tiers-lieux.org/channel/TiBillet
- https://chat.communecter.org/channel/Tibillet

### Sources, veille et inspirations

Sur la supercherie ultra libérale du web3 et des applications décentralisés (Dapp) :
- https://web3isgoinggreat.com/

Sur la monnaie fondante et son auteur : 
- https://fr.wikipedia.org/wiki/Monnaie_fondante
- https://fr.wikipedia.org/wiki/%C3%89conomie_libre

Sur les relations entre consommation, écologie et crypto : 
- https://app.wallabag.it/share/64e5b408043f56.08463016
- https://www.nextinpact.com/article/72029/ia-crypto-monnaie-publicite-chiffrement-lusage-numerique-face-a-son-empreinte-ecologique

Sur les consensus de validation de blockchain :

- https://academy.binance.com/fr/articles/proof-of-authority-explained?hide=stickyBar
- https://github.com/P2Enjoy/proof-of-consensus
- https://www.geeksforgeeks.org/proof-of-stake-pos-in-blockchain/?ref=lbp
- https://www.geeksforgeeks.org/delegated-proof-of-stake/?ref=lbp
