# Skin V2 — DA v1 : points laissés de côté / V2 skin — DA v1: deferred items

**Date :** 2026-09-11
**Origine :** intégration de la maquette `TEMP-tibillet-lespass-main/` (commit
49d31d0 « Direction artistique v1 ») dans `pages/templates/pages/V2/`.
Voir `CHANGELOG/2026-09-11-v2-da-v1-luciole-unbounded.md`.

Le chantier ne touchait que le HTML et le CSS (plus quelques points Python
validés). Tout ce qui demande des **données** ou une **décision** est listé ici.
Dans les gabarits, chaque point est repéré par un marqueur `V2-HERE`
(`rg -n "V2-HERE" pages/`).
/ Everything needing data or a decision is listed here; templates carry a
`V2-HERE` marker.

---

## 1. Modifications Python à faire / Python changes needed

| # | Vue / modèle | Donnée à fournir | Section concernée |
|---|---|---|---|
| R1 | `EventMVT.list` et `EventMVT.partial_list` | `event.price_min` n'est pas un champ du modèle : il est calculé par `index()` et `EventMVT.retrieve`, mais pas par les listes de l'agenda | Prix des cartes événement dans l'agenda |
| R2 | `index()` | Initiatives en cours (app crowds) | Accueil « Ce qui se prépare » |
| R3 | `index()` | Produits : adhésions et services | Accueil « Adhésion & services » |
| R4 | `Configuration` | Champ horaires d'ouverture (n'existe pas) | Accueil, fiche « Horaires » |
| R5 | `EventMVT.retrieve` | 3 autres événements à venir | Page événement « D'autres événements » |
| R6 | `Event` | Partenaires / co-organisateurs (aucun modèle) | Page événement « Partenaires » |
| R7 | `EventMVT.retrieve` | Export agenda `.ics` par événement | Bouton « Ajouter à mon agenda » |
| R8 | `MyAccount.list` | Lieux fréquentés (adhésions, réservations, cartes) | Mon espace « Y retourner » |
| R9 | `MyAccount.list` | Participations crowds de l'utilisateur | Mon espace « Mes contributions » |
| R10 | Nouveau modèle + endpoint | Lieux épinglés par l'utilisateur | Mon espace « Mes lieux » + bouton `pin-btn` |
| R11 | Préférence utilisateur + endpoint | Ordre des modules | Glisser-déposer des modules de Mon espace |
| R12 | `crowds/views.py` | Rendre via `gabarit_skin()` au lieu de chemins de gabarit fixes | Page « Contribuer » en V2 + bouton « Je veux contribuer » |
| R13 | `Event` | Un vrai programme de sous-événements. `Event.children` sert aux **actions bénévoles**, pas à un programme | Page événement « Le programme » (`.ledger`) |
| R14 | `MyAccount.list` | Filtrer `reservations` sur les événements à venir (aujourd'hui passé + futur) | Mon espace « Mon agenda » |
| R15 | `ApiBillet/views.py` `CancelSubscription` | Rendre la carte via `gabarit_skin()` : aujourd'hui elle rend le gabarit **classic**, même sous V2 | Arrêt du prélèvement dans « Mes adhésions » (la carte rafraîchie change de style) |

## 2. Décisions à prendre / Decisions to make

- **Footer** : cibles des liens « Le réseau des lieux », « Journal », « À propos »
  (masqués) ; URL de « Faire un don à TiBillet » (`href="#"`).
  **2026-09-13** : liens laissés masqués et `href="#"` gardé, en attente des cibles.
  La marque « TiBillet » est désormais un lien vers https://tibillet.coop (point
  sorti, voir `2026-09-13-v2-points-laisses-de-cote-nettoyage.md`).
- **Mode sombre** : la DA v1 n'en a pas. `#themeToggle` (barre du haut) et
  `#darkThemeCheck` (préférences) sont masqués en V2. Le test E2E
  `tests/e2e/test_theme_language.py` échouerait si le skin V2 passait en E2E.
  **2026-09-13** : le shell V2 fixe désormais `data-bs-theme="light"` et ne charge
  plus `theme-switcher.mjs` (un thème sombre choisi sur un autre skin fuyait sur le V2).
  La décision « mode sombre ou pas » reste ouverte (reportée le 2026-09-13). Voir `2026-09-13-v2-style-relecture-hallmark.md`.
- **Boutons notifications et paramètres** de la maquette : aucune fonction
  derrière, masqués. Conservés en commentaire (décision du 2026-09-13) ; leurs
  styles sont dans `pages/static/V2/css/V2-reserve.css`.
- **Filtres avancés de l'agenda** (accès, présence, genre, moment, « voir autour
  du lieu », partenariat) : aucun filtre serveur ne correspond, masqués.
  Conservés en commentaire (2026-09-13) ; styles en réserve.

## 3. Nettoyage / Cleanup

**2026-09-13 : les quatre points de cette section sont traités** et sortis
d'ici — voir `CHANGELOG/2026-09-13-v2-points-laisses-de-cote-nettoyage.md`
(ancienne carte en commentaire supprimée ; `main_old` déjà absent du dépôt ;
les deux gabarits V2 orphelins supprimés ; id `badgeOut` rendu unique ; fichiers
de maquette obsolètes supprimés).

## 4. Sécurité à vérifier / Security check

- Les gabarits SECTION (existants et nouveaux EQUIPE / FRISE / RESSOURCES)
  rendent `bloc.texte|safe`. Vérifier que ce champ est bien nettoyé à la saisie
  (admin **et** API v2), sinon passer par un filtre de nettoyage au rendu.

## 5. Opérations / Operations

- **Migration à appliquer** : `pages/migrations/0003_alter_bloc_affichage.py`
  (nouveaux choix EQUIPE / FRISE / RESSOURCES sur `Bloc.affichage`). Aucun
  changement de schéma SQL, mais Django l'applique schéma par schéma :
  `docker exec lespass_django poetry run python manage.py migrate_schemas`
- **Traductions** : nouvelles chaînes `{% translate %}` / `_()` non extraites
  (workflow makemessages / compilemessages à lancer par le mainteneur).
- **2026-09-13** : ces deux opérations restent à faire. Elles n'ont pas pu être
  lancées pendant la session (docker indisponible ; traductions réservées au
  mainteneur). La migration `0004_alter_bloc_affichage.py` (choix VERTICAL /
  HORIZONTAL du bloc LIEU) s'ajoute à la `0003` : même commande.
