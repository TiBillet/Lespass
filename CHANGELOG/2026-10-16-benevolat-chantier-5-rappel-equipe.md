# Bénévolat, chantier 5 : rappel de la veille, « Je ne peux plus venir », inscription par l'équipe / Volunteering, step 5: reminder, withdrawal link, team sign-up

**Date :** 2026-10-16
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- **Rappel la veille** : chaque matin à 8h UTC, un mail à chaque personne inscrite à un besoin de demain (demain dans le fuseau du lieu), dans tous les lieux. Une seule fois par inscription (`rappel_envoye_le`). Un besoin « Journée » a sa propre phrase.
- **Lien « Je ne peux plus venir »** dans le mail de rappel et dans le mail de confirmation : signé (uuid de l'inscription), il marche sans être connecté·e et même après le délai de retrait. Le clic ouvre une page de confirmation ; seul le bouton (POST, jeton CSRF) retire. Après le délai, l'équipe est prévenue (même règle que « Me retirer »). Lien faux, d'un autre lieu, déjà utilisé ou besoin passé : « Ce lien ne marche plus ».
- **Inscrire quelqu'un à sa place** (équipe du lieu seulement) : sur chaque besoin, « Inscrire quelqu'un » ouvre une fenêtre avec une recherche par prénom, nom ou email parmi les personnes du lieu, ou la création d'un compte (email, prénom, nom). L'inscription garde l'admin dans `inscrit_par`, sans contrôle d'adhésion. La personne reçoit « L'équipe de <lieu> t'a inscrit·e », avec le lien « Je ne peux plus venir ».
/ Day-before reminder, signed withdrawal link in both emails, team sign-up with search.

**Pourquoi / Why :** chantier 5 de `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` (§5.9, §5.10, D16, D23, D27).

Sécurité :
- le jeton signe l'uuid, jamais un entier : la `SECRET_KEY` est commune à tous les lieux ;
- la recherche et le pk posté passent par `HumanUser.objects` (personnes du lieu seulement) ;
- les trois vues de l'équipe revérifient l'admin du lieu (403 sinon) ;
- les vues DRF sont exemptées du CSRF pour un visiteur non connecté : le POST du désistement le vérifie lui-même (`jeton_csrf_valide`).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/benevolat.py` | `jeton_de_desistement`, `inscription_du_jeton`, `retirer_une_inscription` (commun au bouton et au lien), lien admin dans la grille |
| `booking/views_benevolat.py` | `desistement`, `inscrire_une_personne`, `chercher_une_personne`, `InscriptionParLEquipeSerializer`, `jeton_csrf_valide` |
| `booking/urls.py` | Trois routes (la lettre reste avant le désistement) |
| `booking/tasks.py` | `rappeler_les_benevoles_du_lendemain[_du_lieu]`, lien de désistement dans la confirmation |
| `TiBillet/celery.py` | `cron_rappel_des_benevoles`, 8h UTC |
| `booking/templates/booking/benevolat/` | `desistement.html`, `partials/{inscrire_une_personne,resultats_personnes}.html`, `emails/rappel.html`, lien dans `emails/confirmation.html` et `partials/besoin.html` |
| `booking/static/booking/css/benevolat.css` | Fenêtre de l'équipe, page de désistement |
| `tests/pytest/test_benevolat_rappel.py` | 11 tests (rappel, lien, CSRF, liens morts) |
| `tests/pytest/test_benevolat_equipe.py` | 23 tests (droits, recherche, autre lieu, création, nom non réécrit) |
| `tests/e2e/test_benevolat_flow.py` | E2E « l'équipe inscrit quelqu'un par la recherche » |

Tous les nouveaux tests ont été vus échouer sur une mutation volontaire (21 mutations).
i18n : nouvelles chaînes traduisibles (msgid en français), workflow i18n à lancer par le mainteneur.
**Celery** : redémarrer le beat et les workers pour que `cron_rappel_des_benevoles` soit programmé.

---

## Comment tester (a la main) / Manual test

### Test 1 — inscrire quelqu'un
1. Connecté·e en admin du lieu, page d'un planning → « Inscrire quelqu'un » sous un besoin.
2. Taper 2 lettres d'un prénom connu du lieu → « Inscrire ».
3. Attendu : la fenêtre se ferme, la case montre le prénom, toast « … est inscrit·e ». Admin → Inscriptions bénévoles : colonne « Inscrit·e par » remplie.
4. « Pas dans la liste ? » avec un email nouveau → compte créé, inscrit, mail « L'équipe … t'a inscrit·e ».

### Test 2 — lien « Je ne peux plus venir »
1. S'inscrire à un besoin, ouvrir le mail de confirmation, cliquer « Je ne peux plus venir » (dans une navigation privée).
2. Attendu : une page de confirmation, rien n'est retiré. « Oui, je ne peux plus venir » → retiré.
3. Recliquer le lien : « Ce lien ne marche plus ».

### Test 3 — rappel
1. S'inscrire à un besoin de demain.
2. `docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from booking.tasks import rappeler_les_benevoles_du_lendemain; rappeler_les_benevoles_du_lendemain()"`
3. Attendu : un mail « Demain 18h–21h : … Merci ! » ; relancer la commande n'envoie rien de plus.

### Verifs automatiques
- `docker exec -w /DjangoFiles lespass_django poetry run pytest tests/pytest/test_benevolat_rappel.py tests/pytest/test_benevolat_equipe.py -q`
- `make e2e benevolat`
