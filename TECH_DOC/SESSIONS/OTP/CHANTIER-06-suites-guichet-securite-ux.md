# OTP — Chantier 06 : suites du guichet de connexion (sécurité, ménage, UX)

**Ouvert le :** 2026-10-20
**Statut :** relevé fait, corrections à planifier. Seule la déconnexion en POST est faite (commit `d3deb365`).
**Chantier d'origine :** [`CHANTIER-02-connexion-par-code-guichet.md`](CHANTIER-02-connexion-par-code-guichet.md), commit `97ebfb36`.

Ce fichier regroupe trois sources :
- la **relecture de sécurité** du commit `97ebfb36` par un agent Fable, comparée à l'état de l'art (OWASP ASVS, NIST SP 800-63B, RFC 9700) ;
- l'**inventaire de l'ancien code qui attendait la validation de l'email** ;
- les **décisions du mainteneur** du 2026-10-20.

Les numéros de ligne datent du 2026-10-20. Ils bougent : se fier d'abord au nom de la fonction.

---

## 1. Décisions du mainteneur (2026-10-20)

| # | Décision | État |
|---|---|---|
| D-POST | `/deconnexion/`, `/logout/` et `/admin/logout/` n'acceptent que le POST avec le jeton CSRF. Un GET reçoit une 405. (Spec AUTH §12, E2.) | **Fait** (commit `d3deb365`), 4 tests ajoutés, vus échouer par mutation. E2E et rendu V2 pas encore vérifiés (serveur arrêté) |
| D-UX | « Se connecter » (navbar, footer) mène **directement** au guichet, sans passer par le panneau `#loginPanel`. Le panneau ne sert plus que lorsqu'une **action** demande d'être connecté (réserver, adhérer, panier, bénévolat). Il dit : « Pour vérifier que vous êtes un humain, connectez-vous pour réserver », puis un bouton mène au guichet | À faire, voir §4 |
| D-SIMPLE | **Pas de formulaire email sur le lieu.** L'email et le code restent sur le guichet. On veut une UX plus agréable, pas plus de code ni de surface d'attaque | Tranché. L'idée du modal email sur le lieu (« D17 ») est abandonnée |
| E1 | `on_commit` dans `reservation_paid` | **En attente**, voir §3.4 |

---

## 2. Relecture de sécurité (Fable)

**Aucun point CRITIQUE** : personne ne peut se connecter au compte d'un autre sans un prérequis extérieur.

### 2.1 IMPORTANT

**I-1. Le code à 6 chiffres est écrit en clair dans les journaux de prod, et part dans Sentry.** *(vérifié)*
- L'objet du mail commence par le code (`AuthBillet/otp_service.py`, `"%(code)s – votre code de vérification"`).
- `CeleryMailerClass.send()` (`BaseBillet/tasks.py:112`) écrit `self.title` en INFO, qui est le niveau de prod (`settings.py`, `LOGGING_LVL`).
- L'intégration Celery de Sentry joint les arguments de la tâche, `(email, code, langue)`, à tout événement d'erreur. Si l'envoi SMTP échoue, Sentry reçoit l'email et un code encore valable environ 8 minutes. Les `logger.info` partent aussi en breadcrumbs.
- Réf. : ASVS V7.1.1, NIST 800-63B §5.1.1.2.
- **Correctif** : ne plus journaliser le titre à `tasks.py:112` (journaliser le gabarit à la place). Ajouter un `before_send` Sentry qui retire `extra["celery-job"]["args"]` pour `code_de_connexion_celery_mailer`.
- **Priorité : la plus haute.**

**I-2. Cookies sans préfixe `__Host-` : un sous-domaine piégé peut poser un faux cookie de session sur le guichet (cookie tossing).**
- Les cookies sont host-only, `Secure`, `HttpOnly` et `SameSite=Lax`. Mais un script sur `x.tibillet.coop` peut **poser** `sessionid=…; domain=.tibillet.coop`, et le navigateur l'envoie au guichet.
- Scénario A : l'attaquant pose sa propre session guichet dans le navigateur de la victime. La victime clique « Se connecter » sur un lieu : le guichet émet un ticket **pour le compte de l'attaquant**, et le `state` passe, puisque c'est bien celui de la victime. La victime réserve et paie pour l'attaquant.
- Scénario B : même chose avec `csrftoken`, puis un POST vers `/sso/code/verifier/`. `CSRF_TRUSTED_ORIGINS` accepte `https://*.{DOMAIN}`.
- Prérequis : un XSS sur n'importe quel sous-domaine. Les canaux volontaires sont déjà fermés (nh3, `/media` filtré, `javascript:` filtré). C'est donc une défense en profondeur, mais le guichet porte l'identité de tous les lieux.
- Réf. : OWASP Session Management Cheat Sheet, ASVS V3.4.4, RFC 6265bis §4.1.3.
- **Correctif** : en prod, `SESSION_COOKIE_NAME = '__Host-sessionid'` et `CSRF_COOKIE_NAME = '__Host-csrftoken'`.
- Conséquences :
  - tout le monde est déconnecté une fois, au déploiement ;
  - `laboutik/templates/laboutik/partial/hx_liste_ventes.html:166` lit le cookie `csrftoken` par son nom, il faut l'adapter ;
  - à étudier : retirer le joker `https://*.{DOMAIN}` de `CSRF_TRUSTED_ORIGINS`, après avoir vérifié qu'aucun POST ne passe d'un sous-domaine à l'autre.

**I-3. L'ancien lien `/emailconfirmation/<token>` est une porte dérobée.**
- `get_connect_token()` (`AuthBillet/models.py`) est un `TimestampSigner()` sans sel. `activate()` (`AuthBillet/views.py`) accepte le lien pendant 72 h. Il n'est **pas à usage unique**, il n'est lié à aucune session, il force `is_active` et `email_valid`, et il ne contrôle pas `espece`.
- Pire : `go_admin` (superuser) et `connect_to` (admin de lieu), dans `Administration/admin_tenant.py`, mettent **un jeton d'admin dans l'adresse**. Il reste dans l'historique et l'`access_log` nginx, et on peut le rejouer pendant 72 h.
- Autres producteurs :
  - `ScanQrCode.link`, `resend_activation_email` ;
  - `get_or_create_user` (API v2, validators) ;
  - `redirect_session_to_another_tenant` (scan & pay) ;
  - `onboard/views.py`, `forge_admin_magic_link`.
- Réf. : NIST 800-63B §5.1.3, ASVS V2.7, RFC 9700 §4.3.
- **Correctif en 2 temps** :
  1. `activate()` à usage unique (`caches["verrous"].add` sur l'empreinte du jeton, même motif que l'onboarding), refusé aux comptes non humains.
  2. `go_admin`, `connect_to` et `redirect_session_to_another_tenant` passent par `https://<lieu>/connexion/?next=…` : le guichet fait déjà ce travail. Le jeton 72 h ne sert plus que dans les mails.
- Chantier à part : il touche l'admin et l'onboarding.

**I-4. On peut bloquer la connexion de quelqu'un, indéfiniment.**
- Aucune limite sur `POST /sso/code/verifier/`, et les clés ne dépendent que de l'email (`connexion_par_code.py`). Cinq faux codes en boucle pour l'email d'une victime suffisent : son code reste « bloqué » **sans fin**. La spec AUTH §7 dit « une heure au plus », ce qui est faux.
- Autre moyen : redemander un code pour la victime toutes les 60 s **remplace** le code qu'elle vient de recevoir.
- Réf. : NIST 800-63B §5.2.2 (un verrouillage ne doit pas permettre un déni ciblé).
- **Correctif, côté guichet seulement** : à l'envoi, tirer un jeton `demande = secrets.token_urlsafe(16)`. Il voyage en champ caché de l'étape « code » et entre dans les clés (`login_code:<email>:<demande>:empreinte|essais`). L'attaquant ne connaît pas la `demande` de la victime. Il ne reste comme nuisance que le quota de 10 mails par heure et par email.

### 2.2 MINEUR

| # | Constat | Correctif proposé |
|---|---|---|
| M-1 | `AuthBillet/urls.py:31` `activate/<uid>/<token>` passe `uid` à une vue qui ne le prend pas : TypeError, 500 à chaque appel. Aucun lien n'y mène | Supprimer la route |
| M-2 | Le plafond par IP compte l'adresse exacte. En IPv6, un abonné change d'adresse dans son /64 sans effort | Compter par `/64` en IPv6. À vérifier hors dépôt : Traefik ne relaie pas un `X-Forwarded-For` venu du client |
| M-3 | Scan du QR d'une carte (`ScanQrCode.retrieve`) : `login()` sans contrôle `espece`, `is_active=True` sans `email_valid`, GET avec effet de bord. Une carte volée reconnecte le voleur, même après « déconnexion de partout ». Le compte peut réserver avec un email jamais vérifié | Parti pris existant. À trancher : la carte compte-t-elle comme preuve suffisante ? |
| M-4 | Pas de consentement : n'importe quelle page peut envoyer quelqu'un sur `https://lieu-x/connexion/`. Le lieu X apprend alors son identité et l'ajoute à `client_achat`. La session guichet dure 12 semaines, superusers compris : on entre dans l'admin de tous les lieux sans retaper de code | Redemander un code aux comptes `is_staff` après N jours ; ou une confirmation la première fois qu'on entre dans un lieu |
| M-5 | Pas de CSP sur le guichet ; HSTS à `max-age=86400` (`nginx_prod/lespass_prod.conf:150`) | `default-src 'self'` sur le guichet ; HSTS d'au moins 1 an |
| M-6 | `sso/partials/etape_email.html` et `etape_code.html` : pas de `{% csrf_token %}` dans les `<form>`. Sans JavaScript, on reçoit une 403 | Ajouter `{% csrf_token %}` |
| M-7 | Signatures sans sel : `get_connect_token`, `Pair`/`pairing_code`, `connexion_celery_mailer` | Ajouter un `salt=` à l'occasion d'une modification |
| M-8 | Le ticket et le `state` passent dans l'adresse de `connexion_retour` (logs nginx). Validité 60 s, usage unique | Pour mémoire, conforme RFC 9700 |
| M-9 | Les essais et l'empreinte sont deux clés memcached. Si la mémoire manque, memcached peut effacer la seule clé `essais` : le compteur repart à 0 | À surveiller sous la charge d'un festival |
| M-10 | `finaliser_le_compte` et `activate()` remettent `is_active=True`. Ce n'est pas exploitable aujourd'hui | Si `is_active=False` sert un jour à bannir, distinguer « jamais activé » et « désactivé » |
| M-11 | Emails et IP en `logger.warning` | Penser à la durée de conservation des logs |

### 2.3 Vérifié et conforme (résumé)

- **OTP** :
  - `secrets` et 6 chiffres, valable 600 s, 5 essais comptés **avant** la comparaison (`add` + `incr` atomiques) ;
  - `compare_digest` sur `salted_hmac` ; usage unique par `delete()` qui renvoie un booléen ; le renvoi d'un code tue l'ancien ;
  - pas d'énumération à l'étape « email » ; si memcached tombe, la vérification refuse tout ;
  - email normalisé (`strip().lower()`) ; clés sur `public`.
- **SSO** :
  - pas de redirection ouverte (`lieu` doit être un `Domain` connu, `next` est vérifié et reste dans la session du lieu) ;
  - `state` de 32 octets, retiré de la session avant la comparaison, comparé à temps constant ;
  - ticket signé avec un sel dédié, valable 60 s, à usage unique, lié au domaine ;
  - `login()` fait `cycle_key()` ou `flush()` ;
  - comptes non humains refusés à 4 endroits ;
  - gabarits échappés, `X-Frame-Options: DENY`.
- **Sessions** : la surcharge de `_get_session_auth_hash` est conforme à Django 4.2 ; jeton vide = empreinte Django ; « déconnexion de partout » effective dès la requête suivante.
- **Anciens chemins** : OAuth Communecter supprimé ; JWT commenté ; `force_login_for_e2e` seulement en DEBUG ; l'OTP de l'onboarding est propre.

---

## 3. Inventaire : le code qui attendait la validation de l'email

**Conclusion** :
- Toutes les portes publiques exigent une session : réserver, adhérer, panier, booking, crowds, bénévolat. **Aucun nouveau statut `F` n'est produit.**
- Des comptes « en attente » sont **encore créés** par des tiers de confiance : API v2, caisse, admin, import CSV, bénévole inscrit par l'équipe, `/fwh/membership/`, recharge v1. C'est normal : la personne n'est pas devant l'écran. Mais **plus rien n'attend la validation pour envoyer les billets**.

### 3.1 Code mort, à supprimer

- `BaseBillet/services_commande.py:563` et `:570` : branche « sinon `F` » du panier gratuit. `PanierMVT.checkout` exige une connexion.
- `booking/booking_engine.py:855` : branche « sinon `FR` ». `member=request.user`.
- `AuthBillet/urls.py:31` : route `activate/<uid>/<token>` (M-1).
- `AuthBillet/views.py`, `class create_user`, et l'import de `CreateUserValidator` : la route est commentée, rien n'y fait référence.

### 3.2 Textes faux, à corriger

- Libellé du statut `FA` « Email verified » (`BaseBillet/models.py`, `booking/models.py`) : `FA` est posé sans vérification (D15).
- `BaseBillet/views.py`, `action_reservation` : « You are going to receive a validation email.. ».
- `commun/adhesion/pending_manual_validation.html` et `free_confirmed.html` : « validez votre email pour réserver ». Réserver n'exige pas `email_valid`.
- Commentaire de `method_F` (`BaseBillet/validators.py`).

### 3.3 À garder pour le stock de `F` déjà en production

Ce code ne sert plus qu'aux réservations `F` créées avant le chantier AUTH :
- l'activateur `activator_free_reservation` et la transition `F → FA` (`BaseBillet/signals.py`) ;
- le nettoyage dans `finaliser_le_compte` ;
- le bouton admin « Valider et envoyer » ;
- les listes et jauges qui comptent `F`/`FR` ;
- le filtre `status=FREERES` de l'API v2.

**À faire** : compter les `F` en prod (commande en lecture seule). Quand il n'en reste plus, ou que leurs événements sont passés, tout ce code peut partir.

### 3.4 `reservation_paid` et `on_commit` (décision E1)

`reservation_paid` tourne dans le **pre_save** de la réservation. `webhook_reservation.delay()` et `ticket_celery_mailer.delay()` partent hors `on_commit`.

- **API v2** (`with transaction.atomic()`) et **panier gratuit** (`atomic` SERIALIZABLE) : la réservation est encore dans le brouillon quand Celery la cherche.
  - `webhook_reservation` ne réessaie pas : `DoesNotExist`, et le **webhook est perdu**.
  - `ticket_celery_mailer` réessaie pendant 10 s. Si la transaction est annulée, ou dure plus longtemps : AttributeError, et le mail ne part pas.
- **Les autres chemins** (Stripe, front, activation, bouton admin) tournent en autocommit. Là, `on_commit` part tout de suite : ça ne change rien.
- **Ce n'est pas lié** au ménage « validation de l'email ». D15 a rendu le cas plus fréquent sur l'API v2.
- **Recommandation** : passer les deux appels en `transaction.on_commit`, dans le style de `signals.py:640-644`.
- Tests à adapter :
  - l'ordre de `test_caracterisation_en_ligne.py:400-405` ;
  - les tests qui patchent `.delay` sans `django_capture_on_commit_callbacks` : `test_reservation_gratuite_validee_tout_de_suite.py`, et à vérifier `test_reservation_admin_envoi_mail.py` et `test_sso_guichet.py:150`.
- Autres `.delay()` hors `on_commit`, à regarder au même moment :
  - `signals.py:313` `check_reward`, protégé par un `time.sleep(1)` ;
  - `crowds/signals.py:74` et `:116` ;
  - `validators.py:1213-1214` ;
  - `ApiBillet/views.py:1243`, `:1281` et `:1353`.

### 3.5 Effets de bord et portes à surveiller

- **`email_error`** : posé quand le mail « Confirmez » revient en erreur (`tasks.py:1613`). Ensuite `get_or_create_user` renvoie `None`. La caisse (`laboutik/views.py`, « Identification obligatoire ») et l'API v2 ne peuvent plus identifier la personne, jusqu'à ce qu'elle se connecte par code. Est-ce voulu ?
- **Session issue d'un scan de carte** : connectée avec `email_valid=False`. Elle reçoit un mail « Confirmez » à chaque réservation ou adhésion, et le bandeau « Resend validation email » s'affiche.
- **`/fwh/membership/<uuid>/`** (`fedow_connect/views.py`, AllowAny, GET) : seule création d'adhésion possible sans aucune authentification. Elle repose sur la transaction relue chez Fedow. À faire relire.
- **`Badge.badge_in`** est en AllowAny : sans doute une erreur 500 pour un anonyme. Hors sujet.

---

## 4. UX : « Se connecter » sans détour (D-UX)

**Constat.** Aujourd'hui, « Se connecter » ouvre le panneau `#loginPanel`, qui ne contient qu'un texte et **un second bouton « Se connecter »** : c'est un clic de trop.

**Plan (simple, aucun nouveau code serveur)** :
1. Navbar et footer des 3 skins (`pages/templates/pages/{classic,V2,faire_festival}/partials/navbar.html`, `footer.html`) : le bouton devient un lien `href="/connexion/?next={{ request.get_full_path|urlencode }}"`. Il n'y a plus de `data-bs-toggle`.
2. `commun/offcanvas/connexion.html` reste, avec le même id `#loginPanel` (c'est le contrat des skins). Son texte devient : « Pour vérifier que vous êtes un humain, connectez-vous pour réserver. Un code vous sera envoyé par email. Une seule connexion pour tous les lieux TiBillet. » Le JS `data-next` ne change pas.
   À trancher : un texte unique (« pour continuer »), ou un texte selon l'action, porté par un `data-raison` sur le bouton ouvreur ?
3. Les déclencheurs d'**action** gardent le panneau : réservation, adhésion, panier, bénévolat, crowds. L'ouverture automatique (`?login=1`, 403 htmx, session expirée) le garde aussi.
4. Vérifier que l'iframe (page intégrée) ouvre toujours un nouvel onglet : le lien direct de la navbar n'a pas le JS du panneau.
5. Tests à reprendre : `tests/e2e/test_connexion_par_code.py`, `test_skin_faire_festival_navigation.py`, `test_panier_flow.py`.

L'email et le code restent sur le guichet (D-SIMPLE). Le correctif I-4 (jeton `demande`) se fait entièrement côté guichet.

---

## 5. Ordre proposé

1. **Petit et sans risque** : I-1, M-6, M-1, plus §3.1 et §3.2.
2. **Guichet** : I-4 (jeton `demande`), puis D-UX (§4).
3. **E1** (`on_commit`), sur feu vert.
4. **I-3** (lien magique), en chantier à part.
5. **I-2** (`__Host-`), avec la caisse, à un déploiement où une déconnexion générale ne gêne pas.
6. Le reste des mineurs, au fil de l'eau.
