# Guichet de connexion : corrections de la relecture Fable / Login desk: fixes from the Fable review

**Date :** 2026-11-09
**Migration :** Non. Nouveau réglage facultatif : `CONNEXION_CODE_PLAFOND_ECHECS_IP_10_MIN` (100 par défaut).

## Resume / Summary
**Quoi / What :**
1. **Force brute du code (N-1).** Au-delà de 100 codes faux tapés depuis une même adresse IP en 10 minutes, plus aucun code n'est vérifié depuis cette IP jusqu'à la fin de la tranche, même le bon. Message : « Trop de codes faux depuis cette connexion. Réessayez dans 10 minutes. ». Le plafond se règle dans le `.env`.
2. **Le code ne part plus dans les journaux ni dans Sentry (I-1).** `CeleryMailerClass.send()` journalise le nom du gabarit, plus le titre (celui du mail de connexion commence par le code). Sentry : les arguments de la tâche `code_de_connexion_celery_mailer` sont retirés (`before_send`), et les variables ou champs nommés `code` / `code_saisi` sont masqués (`EventScrubber`).
3. **Retour du guichet en échec (N-6).** Ticket expiré, `state` différent, compte refusé : la personne revient sur sa page de départ (déjà contrôlée), plus à l'accueil.
4. **Renvoi refusé (N-7).** « Recevoir un nouveau code » refusé pour trop de demandes : on reste à l'étape du code, puisque le dernier code reçu reste valable.
5. **Focus (N-8).** `autofocus` sur le champ du code, et sur le champ email en cas d'erreur.
6. **`next` encodé dans booking (N-4).** Deux redirections vers la connexion encodent l'adresse de retour.
7. **`?open=` (N-11).** La page des adhésions renvoie l'uuid lu en base, plus la valeur reçue. Le `except:` nu disparaît.
8. **Texte des bénévoles (N-10).** « Login (and confirm your email address) to apply » devient « Postuler » : la validation d'email n'est plus exigée, et le lien mène au guichet.
9. **Accord à la première visite d'un lieu (N-2).** Une personne déjà connectée au guichet qui arrive sur un lieu inconnu de son compte (`User.client_achat`) voit « Vous êtes connecté·e avec <email>. C'est votre première visite sur <lieu>. En continuant, ce lieu connaîtra votre adresse email et votre nom. » et un bouton « Continuer sur <lieu> » (`POST /sso/continuer/`). Les visites suivantes passent sans écran. Sans cet accord, n'importe quel lieu (l'ouverture d'un lieu est libre) pouvait récupérer l'identité de toute personne connectée au guichet en lui faisant suivre un lien. Pas de code redemandé, pas d'écran quand la personne vient de taper son code.
10. **`/my_account/` en anonyme** : direction le guichet, avec le retour sur la page du compte demandée (lien « voir mes billets » d'un mail, session expirée). Avant : l'accueil et « Please login to access this page. ».

/ 1. Per-IP cap on wrong codes (brute force). 2. The login code no longer reaches logs or Sentry. 3. Failed desk return goes back to the starting page. 4. Refused resend stays on the code step. 5. Autofocus. 6. Encoded `next` in booking. 7. `?open=` returns the database uuid. 8. Volunteer button text. 9. Anonymous `/my_account/` goes to the desk.

**Pourquoi / Why :** relecture de sécurité et d'UX du guichet, demandée avant de livrer le SSO. Correctifs minimaux, sans nouvelle brique.

**Écartés / Not done :**
- **N-3** (n'accepter que le domaine principal d'un lieu) : si un lieu n'a aucun domaine marqué principal en prod, il ne pourrait plus se connecter du tout. Vérification en lecture seule à faire en prod avant de l'appliquer (voir plus bas).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `AuthBillet/views_sso.py` (N-2) | `le_compte_connait_deja_le_lieu()`, écran d'accord dans `guichet()`, vue `continuer_vers_le_lieu` |
| `AuthBillet/templates/sso/partials/etape_consentement.html`, `TiBillet/urls_public.py` | Nouveau partiel ; route `sso/continuer/` |
| `tests/e2e/test_connexion_par_code.py` | Écran d'accord sur le 2ᵉ lieu ; après « Me déconnecter », le guichet redemande l'email |
| `AuthBillet/connexion_par_code.py` | `cle_cache_ip_echecs()`, plafond de codes faux par IP dans `verifier_le_code_de_connexion(…, adresse_ip)` |
| `AuthBillet/views_sso.py` | IP passée à la vérification ; message `trop_d_essais_ip` ; renvoi refusé → étape du code |
| `AuthBillet/templates/sso/partials/etape_code.html`, `etape_email.html` | Champ caché `renvoi`, `autofocus` |
| `TiBillet/settings.py`, `env_example` | `CONNEXION_CODE_PLAFOND_ECHECS_IP_10_MIN` ; Sentry `before_send` + `EventScrubber` |
| `BaseBillet/tasks.py` | `CeleryMailerClass` journalise le gabarit, pas le titre |
| `BaseBillet/views.py` | `connexion_retour` : retour sur la page de départ en cas d'échec ; `MyAccount.dispatch` → guichet ; `?open=` lu en base |
| `booking/views.py` | `next` encodé |
| `pages/templates/pages/{classic,V2}/partials/evenement_benevoles.html` | « Postuler » |
| `tests/pytest/test_connexion_par_code.py`, `test_sso_guichet.py`, `test_achat_reserve_aux_connectes.py` | Plafond par IP, renvoi refusé, retour en échec, `/my_account/` anonyme |

Chaînes traduisibles ajoutées (msgid FR) : « Vous êtes connecté·e avec <strong>%(email)s</strong>. », « C'est votre première visite sur %(nom_du_lieu)s. En continuant, ce lieu connaîtra votre adresse email et votre nom. », « Continuer sur %(nom_du_lieu)s », « Annuler », « Trop de codes faux depuis cette connexion. Réessayez dans 10 minutes. », « Trop de demandes. Le dernier code reçu reste valable 10 minutes. », « Postuler ». Le workflow i18n est à lancer.

---

## Comment tester (a la main) / Manual test
### Test 1 — plafond de codes faux
1. Dans le `.env`, `CONNEXION_CODE_PLAFOND_ECHECS_IP_10_MIN=3`, redémarrer.
2. Sur le guichet, demander un code, taper 3 codes faux.
3. Attendu au 4ᵉ essai, même avec le bon code : « Trop de codes faux depuis cette connexion… ». Remettre le réglage.

### Test 2 — retour en échec
1. Déconnecté, ouvrir `/connexion/?next=/event/<slug>/` (on part au guichet), puis revenir sur le lieu et ouvrir à la main `/connexion/retour/?ticket=faux&state=faux`.
2. Attendu : retour sur l'événement (pas l'accueil), message « Le lien de connexion a expiré. Reconnectez-vous. ».

### Test 3 — accord à la première visite
1. Se connecter sur `lespass`. Ouvrir `festival` et cliquer « Connexion ».
2. Attendu : le guichet aux couleurs du festival, « Vous êtes connecté·e avec … », bouton « Continuer sur Festival ». Pas de code demandé.
3. Continuer : connecté sur festival. Se déconnecter puis se reconnecter : plus d'écran d'accord pour festival.

### Test 4 — `/my_account/`
1. Déconnecté, ouvrir `/my_account/my_reservations/`. Attendu : le guichet ; après le code, retour sur « Mes réservations ».

### Vérification en prod avant N-3 (lecture seule)
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from Customers.models import Client, Domain
sans = [c.schema_name for c in Client.objects.exclude(schema_name='public') if Domain.objects.filter(tenant=c).exists() and not Domain.objects.filter(tenant=c, is_primary=True).exists()]
print(len(sans), sans[:20])"
```
Si le résultat est `0 []`, N-3 tient en une ligne (`AuthBillet/sso.py`, `trouver_le_lieu_du_domaine` : `.filter(domain=domaine, is_primary=True)`).

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_connexion_par_code.py tests/pytest/test_sso_guichet.py tests/pytest/test_achat_reserve_aux_connectes.py"`.
- `make e2e ARGS="tests/e2e/test_connexion_par_code.py tests/e2e/test_login.py"`.
