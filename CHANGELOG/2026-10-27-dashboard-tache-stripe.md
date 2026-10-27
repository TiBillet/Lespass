# Tableau de bord : invitation Stripe, plus de tâche CGU / Dashboard: Stripe invitation, no more T&C task

**Date :** 2026-10-27
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- L'encart « Ce qu'il reste à faire » du tableau de bord invite à connecter Stripe tant que le compte n'est pas branché. Le texte explique que Stripe n'est pas nécessaire pour le gratuit, mais indispensable pour vendre en ligne (billetterie, adhésions, ressources), et que la caisse peut s'en passer sans cashless.
- La tâche « Renseigner vos mentions légales » est retirée : le champ `legal_documents` n'est pas modifiable dans l'admin, la tâche ne menait nulle part.
- À la création d'un lieu, la description longue n'est plus pré-remplie avec le texte « Bienvenue dans votre nouvel espace ! » et les liens Discord / Matrix / Mastodon de la coopérative. Elle reste vide : la tâche « Écrire une description longue » s'affiche alors au tableau de bord.

/ The dashboard "What's left to do" notice now invites venues to connect Stripe (optional for free features, required for paid ones). The T&C task is removed (its field is not editable in the admin). New venues no longer get a default long description pointing to the cooperative's channels.

**Pourquoi / Why :** Sans Stripe, rien de payant ne fonctionne, et rien ne le signalait au tableau de bord. La tâche CGU renvoyait vers un champ invisible. Le texte par défaut était public et parlait de nous plutôt que du lieu.
/ Without Stripe nothing paid works and the dashboard said nothing; the T&C task pointed to a hidden field; the default text was public and about us, not the venue.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | Tâche `tache-stripe` (si `stripe_payouts_enabled` est faux) ; retrait de la tâche mentions légales et de `_page_legale_existe()` |
| `Administration/templates/admin/partials/dashboard_taches.html` | Phrase d'en-tête élargie aux paiements en ligne |
| `BaseBillet/validators.py` | `create_tenant` n'écrit plus de texte par défaut dans `long_description` |
| `onboard/tasks.py` | Commentaire mis à jour |
| `TiBillet/seo_indexing.py` | Commentaire : le texte de bienvenue ne concerne plus que les lieux anciens (la constante reste utile) |
| `tests/pytest/test_admin_tableau_de_bord.py` | 3 tests : tâche Stripe présente / absente, plus de tâche mentions légales |

---

## Comment tester (a la main) / Manual test

### Test 1 — lieu sans Stripe
1. Sur un lieu dont `stripe_payouts_enabled` est faux, ouvrir `/admin/`.
2. L'encart « Ce qu'il reste à faire » affiche « Connecter votre compte Stripe » en première ligne, avec le texte d'explication.
3. « Compléter ma configuration » mène à la Configuration ; l'onglet « Paiement (Stripe) » porte le bouton « Link your stripe account ».

### Test 2 — lieu avec Stripe
1. Sur un lieu dont Stripe est connecté, ouvrir `/admin/`.
2. La ligne Stripe n'apparaît pas.

### Test 3 — plus de tâche CGU
1. Sur un lieu sans `legal_documents`, ouvrir `/admin/`.
2. Aucune ligne « Renseigner vos mentions légales ».

### Test 4 — création d'un lieu
1. Créer un lieu par le parcours d'onboarding sans saisir de description longue.
2. La description longue de sa Configuration est vide (plus de texte « Bienvenue… » ni de liens Discord/Matrix/Mastodon).
3. Son tableau de bord affiche « Écrire une description longue ».

### Verifs DB / Playwright
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_tableau_de_bord.py -q
```
