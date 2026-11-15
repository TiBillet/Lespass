# Charge — tenir une très forte affluence (3 festivals, ~100 points de vente)

> **Statut** : idée, spec à écrire. Demande du mainteneur (2026-09-30), pendant le
> chantier 05 (fiche C). Pré-requis : chantier 05 terminé (toutes les ventes écrivent
> leur `Vente`), sujet PRIORITÉ du kiosque traité.

## Le but, en une phrase
Prouver, **par des mesures**, que Lespass tient quand trois festivals tournent en même
temps avec une centaine de points de vente (caisses, tireuses, paiements QR / NFC,
bornes), et que des paiements arrivent au même instant sur le **Fedow local** (V2) et
sur l'**ancien Fedow** (distant).

## Ce qu'on veut savoir
1. **Rien ne se perd** : aucun double débit, aucune vente sans règlement, égalités de
   chaque vente vraies, chaîne des ventes de chaque lieu sans trou ni maillon cassé
   (`verifier_chaine_ventes`), soldes des cartes justes à la fin.
2. **Rien ne bloque** : aucun point de vente n'attend un autre lieu ; un lieu n'attend
   pas le réseau d'un autre poste ; pas d'interblocage (deadlock) en base.
3. **Temps de réponse** : médiane et 95ᵉ centile par geste (paiement caisse, fin de
   tirage, paiement QR), sous charge.
4. **Panne de l'ancien Fedow** (lent, injoignable) : les monnaies locales continuent de
   marcher partout ; seules les parts « ancien Fedow » échouent, proprement.

## Points à surveiller (hypothèses à vérifier, pas des certitudes)
- **Le jeton du lieu** : chaque débit local crédite le portefeuille du lieu
  (`TransactionService.creer` → `select_for_update` sur la ligne `Token` du lieu, par
  monnaie). Tous les points de vente d'un lieu passent par **la même ligne** : c'est le
  premier suspect de goulot d'étranglement.
- **Le verrou du lieu à l'encaissement** (`encaisser_vente` : `pg_advisory_xact_lock`
  par lieu, pour numéroter la chaîne) : les encaissements d'un lieu passent un par un.
  Il doit rester très court (aucun réseau après lui : règle du chantier 05).
- **L'ancien Fedow** : sa propre capacité, ses délais d'expiration (`FedowAPI`), et le
  temps d'attente qu'il impose à la caisse, à la tireuse (badge et fin de service) et
  au QR.
- **Les connexions** : workers Gunicorn / Daphne × connexions PostgreSQL ; Redis
  (Channels, WebSocket des tireuses et des caisses) ; file Celery (mails, tâches).
- **Les requêtes lentes** : rapports temps réel, clôtures pendant le service.
- **La survente de billets en réservation directe** (ajout du 2026-11-13, chantier
  `TODO/BILLETTERIE-jauge-par-produit.md`, hors périmètre) : `ReservationValidator.validate`
  (`BaseBillet/validators.py`) compte les places (jauge de l'événement, du produit, du
  tarif) puis crée la réservation **sans verrou ni transaction**. Deux achats simultanés
  peuvent donc passer tous les deux et dépasser une jauge. Le panier, lui, matérialise en
  `SERIALIZABLE` (`services_commande.py`), et la caisse verrouille l'événement
  (`select_for_update`).
  - Un `select_for_update` sur l'événement dans le validateur garderait le verrou **pendant
    l'appel HTTP à Stripe** (`TicketCreator` crée le paiement dans la même méthode) : en
    rush, toutes les réservations d'un événement passeraient une par une.
  - Piste propre : séparer « compter et créer les billets » (sous verrou, court) de
    « créer le paiement Stripe » (après le commit). Cela touche `TicketCreator`, utilisé
    par plusieurs parcours.
  - À mesurer d'abord : combien de surventes réelles en rush, sachant que les billets en
    cours de paiement (`DUREE_D_UN_PAIEMENT_EN_COURS`) occupent déjà la jauge.
  - Le `SERIALIZABLE` du panier (`services_commande.py`) n'est posé que hors transaction
    déjà ouverte : il protège panier contre panier, pas panier contre réservation directe.
  - À dire aux lieux : sur une petite jauge (10 repas), un dépassement de 1 ou 2 est
    possible en rush.
- **La diffusion WebSocket des jauges** (`broadcast_jauge_event`, remise en service par
  `TODO/BILLETTERIE-jauge-par-produit.md`) : une réservation de N billets déclenche N
  diffusions. À mesurer ; si besoin, une seule diffusion par événement et par transaction.

## Comment (première idée, à discuter)
- Un **environnement dédié** (jamais la base de dev ni la production) : 3 lieux, ~100
  points de vente, des milliers de cartes avec des soldes locaux et distants.
- Un outil de charge HTTP (ex. Locust ou k6) qui rejoue des gestes réalistes : caisse
  (espèces, CB, cashless, cascade), tireuses (badge → `pour_end`), paiements QR / NFC,
  bornes.
- L'ancien Fedow : d'abord un **faux** serveur à latence réglable (0, 200 ms, 2 s,
  injoignable), puis une instance de préproduction réelle.
- À la fin de chaque campagne : un script de contrôle (égalités, chaînes, soldes,
  doubles débits) et les mesures (latences, attentes de verrous, erreurs).

## Ce qu'on NE fait PAS d'abord
Pas d'optimisation « au cas où ». D'abord **mesurer**, ensuite corriger seulement ce
que les mesures montrent (principe du projet : pas de sur-ingénierie).

## À décider par le mainteneur avant d'écrire la spec
- Les chiffres cibles : combien de paiements par seconde, par lieu et au total ? Quel
  temps de réponse maximum acceptable à la caisse et à la tireuse ?
- Où tourne l'environnement de charge, et avec quelle instance de l'ancien Fedow ?
