# Wizard event public — email perdu via le chemin Tiers-Lieux

## Ce qui a été fait

Correction d'un bug : un visiteur **anonyme** qui choisit son lieu via le recensement
national **Tiers-Lieux** perdait son email, et sa proposition était rejetée à la
finalisation (retour au début + message « Merci d'indiquer votre adresse e-mail… »).

Cause : le bouton « Utiliser ce lieu » est un formulaire **distinct** du form principal
de l'étape 1 (imbriqué via HTMX). Le navigateur ne postait donc pas le champ email.
L'action `use_tierslieux` ne stockait jamais l'email en session.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | `use_tierslieux` : capture `email_proposeur` du POST + stockage session (anonyme), garde défensive si vide |
| `BaseBillet/templates/.../wizard/_form_lieu.html` | JS : au **clic** sur « Utiliser ce lieu », injecte l'email dans le form Tiers-Lieux avant l'envoi natif, bloque si vide |
| `tests/pytest/test_event_wizard_unifie.py` | test de régression `test_use_tierslieux_anonyme_garde_email_en_session` |

> ⚠️ **Piège** : le form Tiers-Lieux est **imbriqué** dans le form principal (injecté par HTMX).
> L'événement `submit` d'un form imbriqué **ne remonte pas jusqu'à `document`** — une délégation
> `document.addEventListener('submit', …)` ne se déclenche jamais. On écoute donc le `click` sur le
> bouton (qui bubble toujours) et on injecte l'email avant l'envoi natif. Vérifié en navigateur.

## Tests à réaliser

Prérequis config (tenant lespass) : `FederationConfiguration` →
`module_agenda_participatif = True` et `proposition_anonyme_autorisee = True`.

### Test 1 : Chemin Tiers-Lieux (le bug) — déconnecté
1. Se **déconnecter**.
2. Aller sur l'agenda → « Proposer un évènement » → étape lieu.
3. Saisir un **email** dans le champ « Votre adresse e-mail ».
4. Mode « adresse existante » : taper ≥ 3 caractères pour déclencher la recherche
   nationale → des fiches Tiers-Lieux apparaissent sous la liste locale.
5. Cliquer **« Utiliser ce lieu »** sur une fiche.
6. Valider la carte (étape suivante) → ajouter un évènement → **envoyer la proposition**.
7. **Attendu** : page de remerciement (`/event/wizard/done/`), **pas** de retour au début.
   La proposition est créée (`published=False`, `is_proposal=True`) et liée au compte
   créé/retrouvé depuis l'email.

### Test 2 : Email vide bloqué côté client
1. Même parcours, mais **laisser l'email vide**.
2. Cliquer « Utiliser ce lieu ».
3. **Attendu** : l'envoi est bloqué, le champ email affiche la validation native du
   navigateur (bulle « Veuillez renseigner ce champ ») et reçoit le focus.

### Test 3 : Non-régression chemins classiques
1. **Adresse existante** (sans Tiers-Lieux) + email → finalisation OK.
2. **Nouveau lieu manuel** (nom + carte) + email → finalisation OK.
3. **Connecté** (staff ou simple membre) : aucun champ email demandé, finalisation OK
   via tous les chemins.

### Test automatique
```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_event_wizard_unifie.py tests/pytest/test_tiers_lieux.py -q
```

## Compatibilité

- Aucune migration. Aucune nouvelle chaîne i18n (le message existait déjà).
- Le chemin connecté n'est pas touché (pas d'email requis).
- Garde serveur défensive : un POST forgé vers `use-tierslieux` sans email (anonyme)
  est renvoyé à l'étape 1 avec le message d'email obligatoire.
