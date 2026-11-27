# Se connecter avant de réserver / Log in before booking

**Date :** 2026-11-27
**Migration :** Oui — `BaseBillet/migrations/0246_connexion_obligatoire_pour_reserver.py`
(`docker exec lespass_django poetry run python manage.py migrate_schemas --executor=standard`)

## Resume / Summary
**Quoi / What :** Nouveau réglage du lieu « Se connecter avant de réserver » (Configuration >
Réglages, décoché par défaut). Coché, le bouton « Je veux réserver une ou plusieurs places »
d'une personne non connectée ouvre le panneau de connexion, avec le message « Pour réserver
des places, connectez-vous d'abord. ». Le lien reçu par mail la ramène sur l'événement,
connectée, formulaire de réservation ouvert : elle a alors « Ajouter au panier ».
/ New venue setting: an anonymous booking button opens the login panel; the login link brings
the person back to the event, logged in, booking form open (cart available).

**Pourquoi / Why :** Le panier exige d'être connecté. Sans ce réglage, une personne non
connectée ne voit que « Payer maintenant ». Un lieu qui vend surtout par le panier (pass,
plusieurs événements) peut ainsi faire connecter les gens d'abord.
/ The cart requires login; this lets a venue send people through login first.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Configuration.connexion_obligatoire_pour_reserver` |
| `BaseBillet/migrations/0246_connexion_obligatoire_pour_reserver.py` | Migration du champ |
| `Administration/admin_tenant.py` | Le réglage dans l'onglet « Réglages » de la configuration |
| `BaseBillet/views.py` | `adresse_de_retour_signee_apres_connexion` : la vue `connexion` accepte un `next` du site, le signe et le met dans le lien du mail (et dans le lien « TEST MODE ») |
| `BaseBillet/templates/commun/formulaires/login.html` | Champ caché `next` |
| `BaseBillet/templates/commun/offcanvas/connexion.html` | Message « Pour réserver… » et script qui remplit `next` quand un bouton « réserver » ouvre le panneau |
| `pages/templates/pages/classic/partials/reservation_declencheur.html`, `pages/templates/pages/V2/partials/reservation_declencheur.html`, `pages/templates/pages/faire_festival/vues/evenement.html` | Réglage coché et personne non connectée : le bouton cible `#loginPanel` (`data-testid="booking-open-login"`) avec l'adresse de retour |
| `tests/pytest/test_connexion_avant_de_reserver.py` | Nouveau : 9 tests |
| `tests/pytest/test_admin_configuration_onglets.py` | Le nouveau champ dans la liste attendue |

### Note
- C'est un choix d'affichage : la réservation directe reste acceptée côté serveur pour une
  personne non connectée.
- Une adresse de retour d'un autre site est ignorée (`url_has_allowed_host_and_scheme`).
- Le lien ouvert dans un autre navigateur marche aussi : l'adresse de retour est dans le lien.
- i18n : 3 nouvelles chaînes (verbose_name, help_text, message du panneau), workflow à lancer.

---

## Comment tester (a la main) / Manual test

### Test 1 — réglage coché
1. Admin > Configuration > Réglages : cocher « Se connecter avant de réserver ».
2. Déconnecté, ouvrir un événement et cliquer « Je veux réserver une ou plusieurs places » :
   le panneau de connexion s'ouvre, avec le message « Pour réserver des places,
   connectez-vous d'abord. ».
3. Saisir son email, envoyer. En DEBUG, cliquer le lien « TEST MODE » (sinon, le lien du
   mail) : on revient sur l'événement, connecté, formulaire ouvert, avec « Ajouter au panier ».

### Test 2 — les autres cas
1. Ouvrir la connexion depuis la barre de menu : pas de message, le lien ramène à l'accueil.
2. Connecté, le bouton ouvre directement le formulaire.
3. Réglage décoché : une personne non connectée ouvre le formulaire, comme avant.

### Test 3 — tests automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_connexion_avant_de_reserver.py -q`
- Attendu : 9 passed.
