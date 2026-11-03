# Technique

## Périmètre

- Le logiciel spécifié est l'app Django `booking` : la réservation de
  ressources partagées, et le planning des bénévoles (`benevolat`).
- Il tourne dans Lespass, un projet Django multi-lieux
  (`django-tenants`) : chaque lieu est un tenant, et les données de
  `booking` vivent dans le schéma du tenant.
- Le reste de Lespass est l'environnement de `booking`. La
  spécification ne décrit que ce que `booking` en utilise, par exemple
  les produits, les tarifs et le paiement (`BaseBillet`,
  `PaiementStripe`), les utilisateurs (`AuthBillet`).
- Fichiers partagés qu'un incrément peut modifier :
  - l'admin de `booking`, dans `Administration/` (par exemple
    `Administration/admin/resources.py`,
    `Administration/admin/benevolat.py`) ;
  - le point de montage des URL, `TiBillet/urls_tenants.py` ;
  - le code des autres apps qui appelle `booking`, par exemple le
    panier et les commandes dans `BaseBillet/`.

## Pile et conventions

- La pile et les conventions sont celles de Lespass, dans
  `GUIDELINES.md` à la racine du dépôt : Django, contrôleurs DRF
  `ViewSet`, validation par `Serializer`, HTMX et Bootstrap, texte
  source en français pour les traductions.

## Politique de tests et de qualité

- Les tests du comportement de `booking` vont dans `booking/tests/`,
  avec ses propres fixtures dans `booking/tests/conftest.py`.
- Le comportement que seul un navigateur peut observer va dans
  `tests/e2e/`, sous un marqueur de famille existant de `pytest.ini`
  (par exemple `benevolat`, `billetterie`).
- Les tests tournent dans le conteneur Docker :
  - le contrôle d'une phase :
    `docker exec lespass_django poetry run pytest booking/tests/`, et
    les fichiers de `tests/pytest/` et `tests/e2e/` qui testent la zone
    que l'incrément modifie (`make test` exigerait le serveur live) ;
  - la suite complète, `make test`, est lancée par l'humain, pas par
    l'agent.

## Documents

- `booking/spec/` est la spécification.
- `booking/doc/` contient des notes antérieures, lues comme matière
  pour spécifier une zone. Il est supprimé une fois son contenu
  spécifié ou abandonné.
