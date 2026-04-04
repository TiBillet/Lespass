<h1 align="center">
  <!-- CAPTURE : Logo TiBillet (le logo actuel ou un nouveau si vous en avez un) -->
  <br>
  TiBillet
  <br>
</h1>

<h3 align="center">
  Billetterie, caisse, cashless, adhésion, monnaie locale — fabriqués en commun.
</h3>

<p align="center">
  <a href="https://codecommun.coop">Coopérative Code Commun</a> ·
  <a href="https://tibillet.org">Documentation</a> ·
  <a href="https://codecommun.tibillet.coop/contrib">Budget contributif</a> ·
  <a href="https://discord.gg/ecb5jtP7vY">Discord</a> ·
  <a href="./README.en.md">🇬🇧 English</a>
</p>

<p align="center">
  <img alt="Licence" src="https://img.shields.io/badge/licence-AGPLv3-blue">
  <img alt="Django" src="https://img.shields.io/badge/Django-4.2-green">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11-blue">
  <img alt="Contributeurs" src="https://img.shields.io/badge/contributeur·ices-20-orange">
  <img alt="Lieux" src="https://img.shields.io/badge/lieux%20%26%20orgas-14-purple">
</p>

<!-- CAPTURE : screenshot_hero.png — La capture la plus parlante du projet. Je suggère l'agenda public d'un lieu avec des événements, ou un montage de 2-3 écrans (agenda + caisse + carte NFC). Format large, 1200px minimum. -->

---

## TiBillet, c'est quoi ?

TiBillet est un ensemble d'outils libres pour les lieux culturels, les festivals, les associations et les tiers-lieux : billetterie en ligne, caisse enregistreuse, cashless par carte NFC, gestion d'adhésions, monnaie locale et monnaie temps.

Mais TiBillet n'est pas qu'un logiciel. C'est un **commun numérique**, construit par et pour les gens qui s'en servent. 14 lieux et organisations, 20 contributeur·ices, une coopérative — et l'idée simple que les outils qui font tourner nos lieux de vie ne devraient appartenir à personne d'autre qu'à ceux qui les utilisent.

**Le principe :** une carte NFC unique, valable dans tout le réseau. Pas de frais d'activation, pas de date d'expiration, pas de case à décocher. Vous rechargez quand vous voulez, vous dépensez où vous voulez, vous vous faites rembourser quand vous voulez. Et la carte sert aussi de carte d'adhésion, de porte-monnaie local et de monnaie temps.

> **🇬🇧 English speakers:** TiBillet is a federated, open-source toolkit for ticketing, POS, NFC cashless payments, memberships, and local currencies — built as a digital commons by the [Code Commun Cooperative](https://codecommun.coop). [Read more in English →](./README.en.md)

---

## En production, pour de vrai

TiBillet n'est pas un prototype. C'est un outil en production depuis 2018, né au [Manapany Festival](https://www.manapany-festival.re/) à La Réunion, aujourd'hui déployé sur une dizaine de lieux — des cafés associatifs aux festivals de 15 000 personnes.

<!-- CAPTURE : photo_terrain.jpg — Une photo d'un vrai lieu ou festival avec TiBillet en action (caisse, carte, public). Si possible la Raffinerie ou un festival. C'est cette image qui dit "c'est réel". -->

Quelques exemples de ce que TiBillet rend possible aujourd'hui :

- **4 festivals à Montpellier** partagent la même carte NFC pour 15 000 festivaliers. Une carte, quatre lieux, zéro bracelet jetable.
- **Un collectif citoyen en Normandie** distribue 100 cartes pour de l'aide alimentaire solidaire (Sécurité Sociale de l'Alimentation). Chaque carte est créditée de 100 €, peu importe ce que la personne a payé. Pas de contrôle, pas de case "précaire" à cocher — juste de la dignité.
- **La Raffinerie à La Réunion**, une ancienne sucrière reconvertie en tiers-lieu, utilise une monnaie temps : les heures passées sur les chantiers participatifs du mercredi sont comptabilisées sur la carte, échangeables contre des bières au bar associatif le soir.
- **Des bars associatifs** vérifient l'adhésion automatiquement au scan NFC — fini le fichier Excel que personne ne consultait.

---

## Fonctionnalités

| | Module | Description | Détails |
|---|---|---|---|
| 🎫 | **Billetterie & Agenda** | Événements, tarifs, réservations en ligne, QR codes, scan à l'entrée | [→ BaseBillet/](./BaseBillet/) |
| 🏪 | **Caisse enregistreuse** | Point de vente tactile, grille d'articles, multi-moyens de paiement, conforme LNE | [→ laboutik/](./laboutik/) |
| 💳 | **Cashless NFC** | Carte sans contact, rechargement en ligne ou sur place, paiement fédéré multi-lieux | [→ fedow_core/](./fedow_core/) |
| 🤝 | **Adhésions** | Cotisations en ligne ou sur place, vérification au scan, tarifs préférentiels | [→ BaseBillet/](./BaseBillet/) |
| 🪙 | **Monnaie locale & temps** | Euros, monnaie cadeau, monnaie temps — plusieurs devises sur une seule carte | [→ fedow_core/](./fedow_core/) |
| 📊 | **Rapports & comptabilité** | Clôtures de caisse, export FEC, bilans billetterie, PDF et CSV | [→ laboutik/](./laboutik/) |
| 📦 | **Inventaire** | Stock par produit, alertes, journal de mouvements, mise à jour temps réel | [→ inventaire/](./inventaire/) |
| 🗳️ | **Budget contributif** | Initiatives, votes, financement participatif, co-rémunération transparente | [→ crowds/](./crowds/) |
| 🖨️ | **Impression thermique** | Tickets, reçus, clôtures — Sunmi Cloud, LAN, imprimante interne | [→ laboutik/](./laboutik/) |
| 🌐 | **API sémantique** | Schema.org / JSON-LD, clé API, endpoints REST | [→ api_v2/](./api_v2/) |

<!-- CAPTURES : Pour chaque module, une capture dans le dossier Presentation/ ou docs/img/. Format suggéré : 800x500px, thème clair. Voici la liste :

1. screenshot_agenda.png — Page publique d'un lieu avec la liste des événements à venir
2. screenshot_caisse.png — La grille d'articles POS avec les tuiles (idéalement avec une pastille stock visible)
3. screenshot_cashless.png — L'écran de paiement NFC ou le retour carte avec le solde
4. screenshot_adhesion.png — La page publique d'adhésion ou l'admin avec la liste des membres
5. screenshot_admin_bilan.png — La page bilan billetterie dans l'admin Unfold (montre le côté pro)
6. screenshot_contrib.png — La page /contrib avec les initiatives et budgets
7. screenshot_inventaire.png — La fiche stock admin avec le formulaire d'actions
8. photo_carte_nfc.jpg — Une vraie carte TiBillet recto/verso (le totem physique du projet)
9. screenshot_caisse_festival.png — La caisse en mode festival si le rendu est différent

Optionnels mais impactants :
10. photo_terrain_festival.jpg — Photo de festival ou de lieu avec TiBillet en action
11. schema_architecture.png — Schéma simple de la fédération (lieux + carte partagée + Fedow)
-->

---

## Démarrage rapide

TiBillet tourne dans Docker. Une seule commande pour lancer l'environnement de développement :

```bash
git clone https://github.com/TiBillet/TiBillet.git
cd TiBillet
cp env_example .env        # Configurer les variables d'environnement
docker compose up -d
```

L'application est accessible sur `https://lespass.tibillet.localhost`.
L'admin est sur `https://lespass.tibillet.localhost/admin/` (auto-login en mode développement).

> **Prérequis :** Docker, Docker Compose, et un reverse proxy Traefik (inclus dans le compose).

Pour les détails d'installation, de configuration et de déploiement en production : [→ Documentation complète](https://tibillet.org)

---

## Tests

```bash
# Tests unitaires et intégration (pytest)
docker exec lespass_django poetry run pytest tests/pytest/ -v

# Tests API v2
docker exec lespass_django poetry run pytest -m integration tests/pytest/

# Tests End-to-End (Playwright — un fichier à la fois, toujours workers=1)
cd tests/playwright
yarn playwright test --project=chromium --headed --workers=1 tests/01-login.spec.ts
```

Carte Stripe de test : `4242 4242 4242 4242`, exp `12/42`, CVC `424`.

---

## Architecture

TiBillet est en cours d'unification en **mono-repo**. Les trois services historiques (Lespass, LaBoutik, Fedow) deviennent un seul projet Django multi-tenant :

```
TiBillet (mono-repo)
├── BaseBillet/      Billetterie, adhésions, événements
├── laboutik/        Caisse enregistreuse, POS
├── fedow_core/      Portefeuille fédéré, tokens, multi-devises
├── crowds/          Budget contributif, financement participatif
├── inventaire/      Gestion de stock POS
├── api_v2/          API sémantique schema.org
├── Administration/  Admin Django (Unfold)
├── AuthBillet/      Authentification, SSO
├── PaiementStripe/  Paiements, webhooks Stripe
└── ...
```

**Stack :** Django 4.2, Python 3.11, PostgreSQL 13 (multi-tenant via django-tenants), Redis, Celery, HTMX + Bootstrap 5, Django Channels (WebSocket).

**Pas de SPA, pas de framework JavaScript lourd.** Le rendu est côté serveur. Les interactions dynamiques passent par HTMX. Le JavaScript est minimal (toasts et petites interactions). C'est un choix délibéré : le code doit pouvoir être lu et modifié par des développeur·euses non-expert·es qui rejoignent la coopérative.

---

## Plus qu'un logiciel libre

TiBillet est sous licence AGPLv3. Ça garantit que le code restera libre — personne ne peut le verrouiller, le fermer, le privatiser.

Mais on pense que le logiciel libre, aussi génial soit-il, ne suffit pas. Un dépôt Git avec une licence libre, c'est une ressource ouverte. Ce n'est pas encore un commun. Des tanks roulent sur Linux. Les plus grandes entreprises du monde construisent leur fortune sur du logiciel libre. La licence protège le code. Elle ne protège ni les usages, ni les gens.

**Nous n'avons pas choisi de "faire un commun". On fabrique en commun, parce que TiBillet n'aurait jamais pu être construit autrement.**

La monnaie temps de la Raffinerie, c'est une idée qui a émergé des chantiers du mercredi matin — pas d'un cahier des charges. La SSA en Normandie, c'est un collectif citoyen qui a dit "on a besoin de ça" et qu'on a accompagné sur place. Le mode festival, c'est le retour de dix ans de bénévoles derrière des tireuses à bière à 2h du matin. Aucun de ces usages n'aurait été inventé par une équipe de développeurs seuls dans un bureau, ni par un modèle d'IA entraîné sur du code — parce que ces solutions viennent des gens qui vivent les problèmes, pas de ceux qui imaginent les résoudre.

On s'appuie sur les travaux d'[Elinor Ostrom](https://fr.wikipedia.org/wiki/Elinor_Ostrom) pour penser ce qu'on fait. Un commun, c'est trois choses indissociables :

- **Une ressource partagée** — le logiciel, oui, mais surtout tout ce qu'il permet : l'agenda fédéré, la carte partagée, les données qui restent chez vous.
- **Une communauté vivante** — les lieux qui s'en servent, qui remontent des besoins, qui testent, qui documentent. C'est le point de départ, pas un bonus.
- **Une gouvernance organisée** — la [coopérative Code Commun](https://codecommun.coop), structurée en SCIC avec trois collèges (animateur·ices, contributeur·ices, utilisateur·ices), où chaque voix compte pareil.

> « Un logiciel libre qui dort au fond d'une forge Git ne change pas le monde. Un commun vivant, partagé, documenté et soutenu, si. »
> — [Charte Code Commun](https://codecommun.coop/docs/Fabrique/commun_numerique)

Pour aller plus loin : [Qu'est-ce qu'un commun numérique ?](https://codecommun.coop/docs/Fabrique/commun_numerique) · [Charte et valeurs](https://codecommun.coop/docs/Fabrique/charte)

---

## Contribuer

TiBillet ne fonctionne pas avec des "issues" et des "pull requests" dans le vide. On construit ensemble.

### Le budget contributif

On met les sous sur la table — littéralement. Sur [codecommun.tibillet.coop/contrib](https://codecommun.tibillet.coop/contrib), vous trouverez les chantiers en cours, les budgets associés et les contributions de chacun·e. Vous choisissez une tâche, vous décidez comment vous voulez être rémunéré·e (ou pas — le bénévolat est bienvenu aussi), et c'est validé collectivement.

C'est ce qu'on appelle le **budget contributif** : pas de manager qui attribue les tâches, pas de hiérarchie qui décide des salaires. Chacun·e évalue ses besoins en transparence.

<!-- CAPTURE : screenshot_contrib.png — La page /contrib si pas déjà placée plus haut -->

### Comment on travaille

- **Sessions de pair à pair** — Tous les jeudis et vendredis, en visio, on code ensemble. Pas besoin d'être expert·e.
- **Déplacements sur le terrain** — On ne construit pas depuis un bureau. On va dans les lieux, on installe, on forme, on écoute les retours. C'est comme ça qu'émergent les vraies fonctionnalités.
- **Réunions mensuelles ouvertes** — Le premier lundi de chaque mois, tout le monde est invité. On parle de ce qui marche, de ce qui coince, de ce qu'on veut construire ensuite.
- **Discord & Matrix** — Pour le quotidien, les questions, les coups de main.

### Par où commencer

1. **Venez discuter** sur [Discord](https://discord.gg/ecb5jtP7vY) — on vous accueille, on vous oriente.
2. **Consultez les chantiers** sur le [budget contributif](https://codecommun.tibillet.coop/contrib) — il y a des tâches de tous niveaux, de la documentation à l'architecture Django.
3. **Lisez le [GUIDELINES.md](./GUIDELINES.md)** pour les conventions de code (FALC, HTMX, ViewSets, etc.).
4. **Proposez une idée** — si un besoin revient dans 3-4 lieux, on s'y colle.

> Le code suit le principe **FALC** (Facile À Lire et Comprendre) : noms de variables explicites, commentaires bilingues FR/EN, logique lisible de haut en bas, pas de magie. Parce qu'un commun numérique, ça implique que le code soit accessible à celles et ceux qui veulent s'en emparer.

---

## Qui fabrique TiBillet

TiBillet est porté par la [Coopérative Code Commun](https://codecommun.coop), une SCIC (Société Coopérative d'Intérêt Collectif) basée à La Réunion.

L'équipe permanente :

- **Jonas Turbeaux** — Backend, DevOps, mainteneur. Ancien régisseur de festival et ingé son, bricoleur depuis toujours.
- **Mike Caron** — Hardware, systèmes embarqués, NFC.
- **Nicolas Dijoux** — Frontend senior.
- **Axel Chabran** — Administration, gestion de projet.

Et une vingtaine de contributeur·ices : développeur·euses, documentalistes, testeur·euses, bénévoles de lieux qui remontent des bugs et des idées.

### Fabriqué avec et pour

[La Raffinerie](https://www.laraffinerie.re/) · [Le Bisik](https://bisik.re) · [Le Manapany Festival](https://www.manapany-festival.re/) · [La Réunion des Tiers-Lieux](https://www.communecter.org/costum/co/index/slug/LaReunionDesTiersLieux/) · [Communecter](https://www.communecter.org/) · [CoopCircuit](https://coopcircuit.org/) · et tous les lieux qui utilisent, testent et transforment TiBillet au quotidien.

### Soutiens

- Lauréat **France 2030** — Appel à projet "Billetterie innovante" du ministère de la Culture.
- [JetBrains](https://jb.gg/OpenSourceSupport) — Licences open source.

---

## Licence

[AGPLv3](./LICENSE) — Libre, et ça le restera.

---

## Contact

- **Discord** : [discord.gg/ecb5jtP7vY](https://discord.gg/ecb5jtP7vY)
- **Matrix** : bientôt
- **Email** : [contact@tibillet.re](mailto:contact@tibillet.re)
- **Site** : [tibillet.org](https://tibillet.org)
- **Coopérative** : [codecommun.coop](https://codecommun.coop)
