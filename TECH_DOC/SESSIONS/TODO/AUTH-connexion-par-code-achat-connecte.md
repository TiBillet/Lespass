# AUTH — Connexion par code à 6 chiffres, achat réservé aux personnes connectées

> **Status :** spec du 2026-09-22, **non commencée**. Relue le même jour par un agent Opus
> (exactitude face au code) et un agent Fable (point de vue du mainteneur). Leurs corrections
> sont intégrées.
> **Pré-requis :** aucun.
> **Origine :** audit de la réservation anonyme (2026-09-22).
> **Remplace :** l'idée « CHANTIER-02 — Login OTP » du hub `TECH_DOC/SESSIONS/OTP/INDEX.md`.
> **Décisions :** toutes tranchées par le mainteneur le 2026-09-22 (§2).

## Lexique

| Terme | Sens |
|---|---|
| Code | code à 6 chiffres envoyé par mail, à taper sur le site (OTP) |
| Empreinte | le code passé dans une fonction à sens unique (`hash_code_otp`). On garde l'empreinte, jamais le code |
| Lien magique | lien `/emailconfirmation/<jeton>` envoyé par mail : un clic connecte |
| Compte activé | `is_active=True` et `email_valid=True` |
| Anonyme | visiteur non connecté |
| Réservation `F` / `FA` | réservation gratuite, compte pas encore activé / compte activé |
| Machine à états | `BaseBillet/signals.py` : un `pre_save` qui réagit aux changements de statut. Pour un compte : le passage `is_active` False → True |
| Jauge | nombre de places d'un événement (`jauge_max`) |
| Plafond | nombre maximum de demandes permises dans un temps donné |
| Partiel | morceau de HTML renvoyé à htmx, qui remplace une zone de la page |
| Lieu | un tenant (un schéma PostgreSQL) |

## 1. Pourquoi ce chantier

Aujourd'hui, un anonyme peut réserver un billet ou adhérer. Il tape un email dans le
formulaire. Le site crée un compte non activé à cet email et envoie un lien magique.

- **Billet gratuit** : la réservation reste en `F`. Le clic sur le lien active le compte.
  La machine à états (`signals.py:381`) lance `activator_free_reservation`
  (`signals.py:231`), qui passe la réservation en `FA` et envoie les billets.
- **Billet payant** : Stripe valide le paiement. L'état du compte n'est jamais regardé.
- **Adhésion** : même principe (`MembershipValidator`).

Ce mécanisme a des failles. Les deux relectures les ont confirmées dans le code ; aucune
n'est encore prouvée par un test.

| # | Constat | Où |
|---|---|---|
| A1 | **Un anonyme peut réserver au nom d'un autre.** Il tape l'email d'un compte activé : la réservation gratuite passe en `FA` tout de suite, les billets partent chez cette personne. Cela prend son quota par personne et des places dans la jauge. (Une personne connectée est déjà protégée : `validators.py:661-663`.) | `validators.py:656-665`, `250-253` |
| A2 | **Tarif réservé aux adhérents** : pour un anonyme, le serveur vérifie l'adhésion de l'email *tapé*. Seul le gabarit cache le tarif. | `validators.py:804-810` |
| A3 | Une adhésion à 0 € est validée tout de suite pour n'importe quel email. `MembershipValidator` ne compare jamais l'email tapé à celui de la personne connectée. | `validators.py:1029`, `1099-1124` |
| A4 | Aucun plafond de requêtes sur `/connexion/`, la réservation et l'adhésion (`DEFAULT_THROTTLE_CLASSES` est commenté, `settings.py:461`). On peut inonder une boîte mail. Des réservations gratuites fantômes bloquent la jauge 30 minutes. | `views.py:518`, `3300`, `3436` |
| A5 | `/connexion/` crée le compte et le portefeuille Fedow **avant** toute preuve de l'email. Elle plante (500) si le compte a `email_error=True` : `get_or_create_user` renvoie `None`, puis `user.wallet`. | `views.py:524-527`, `AuthBillet/utils.py:143-145` |
| A6 | Le lien magique marche 72 heures, et plusieurs fois. | `AuthBillet/views.py:135` |
| A7 | `EventMVT.get_permissions()` renvoie toujours `AllowAny`. Le `permission_classes=[IsAuthenticated]` posé sur l'`@action` `action_reservation` est donc ignoré (DRF ne le lit que dans le `get_permissions()` par défaut). Un anonyme l'atteint et obtient une 500. | `views.py:2690-2694`, `3270` |
| A8 | `activator_free_reservation` lève un `ValueError` (événement devenu complet) **dans un `pre_save`**. Django envoie `pre_save` avant l'écriture : l'erreur annule `user.save()`. Le compte n'est pas activé, la personne n'est pas connectée. Il faut recliquer sur le lien. | `signals.py:279-284`, `AuthBillet/views.py:145-147` |

**Le but :** une seule façon d'acheter sur le site, être connecté. Une seule façon de se
connecter, un code reçu par mail. Le reste du site exige déjà la connexion : panier,
réservation de ressource (`booking`), financement participatif (`crowds`).

## 2. Décisions

### 2.1 Tranchées par le mainteneur

| # | Sujet | Décision |
|---|---|---|
| D1 | Adhésion anonyme | **Retirée**, comme la réservation anonyme. |
| D2 | Liaison d'une carte QR (`/qr/link/`) | **Hors chantier, inchangée.** Scan du QR → email → compte créé et connecté. Un autre chantier plus tard. |
| D3 | Lien magique | **Gardé pour l'instant** (liste de ses usages au §5.6). Ce chantier arrête seulement de l'envoyer pour se connecter. Le SSO sera un autre chantier. |
| D4 | Où garder le code | **Cache Django.** Attention : c'est **memcached** (`TiBillet/settings.py:317-324`), pas Redis. Les commentaires de l'onboarding disent « Redis » à tort. |

### 2.2 Proposées par la spec, validées par le mainteneur

| # | Sujet | Proposition |
|---|---|---|
| D5 | Quel service OTP | Les **fonctions pures** de `AuthBillet/otp_service.py`. Pas `OtpSession` : elle range tout en session (voir §3). |
| D6 | Saisie du code | **Un seul champ**, pas 6 cases. Sur iOS, l'app Mail propose le code reçu (`autocomplete="one-time-code"`). Ailleurs, on tape 6 chiffres. Aucun JavaScript. |
| D7 | Mode DEBUG | Le code est écrit dans le journal du serveur. **Aucun code universel.** |
| D8 | API v2, caisse, admin | **Inchangés.** Les validateurs gardent leur champ `email`. La connexion est exigée dans les **vues du site**, pas dans les validateurs. |
| D9 | Plafond par adresse IP | **500 demandes de code par tranche de 10 minutes** (environ 3 000 par heure), réglable sans toucher au code. Détail ci-dessous. |
| D10 | Empreinte du code | `hash_code_otp` passe en `salted_hmac("AuthBillet.otp", code, algorithm="sha256").hexdigest()`. Avec un SHA-256 simple, une copie du cache suffit pour retrouver le code : il n'y a qu'un million de codes possibles. Avec la clé secrète du projet, c'est impossible. Une ligne ; `test_otp_service.py` reste valable (64 caractères hexadécimaux). |
| D11 | `OtpSession` | **Supprimée** avec ses 15 tests (`otp_session.py`, `test_otp_session.py`). Aucun utilisateur, et un raccourci DEBUG qui ouvrirait n'importe quel compte. |
| D12 | Réservations `F` d'événements passés | **Annulées** juste avant l'activation du compte (§5.2). Sinon, la 1re connexion par code enverrait les billets d'événements terminés : l'activateur ne regarde pas la date. |

**Pourquoi D9 est si haut.** Le wifi gratuit d'un festival met des milliers de personnes
derrière **une seule** adresse IP. Les réseaux 4G partagent aussi leurs adresses entre
beaucoup d'abonnés. Exemple : 10 000 festivaliers, 2 000 connexions dans l'heure avant la
tête d'affiche. Un plafond de quelques centaines bloquerait tout le festival.
- **Tranche de 10 minutes**, pas d'une heure : si le plafond est atteint, le blocage dure au
  plus 10 minutes.
- **Réglable sans toucher au code** : `settings.CONNEXION_CODE_PLAFOND_IP_10_MIN`, lu dans
  la variable d'environnement du même nom (500 par défaut), à ajouter dans `env_example`.
  Avant un très gros festival, on l'augmente et on redémarre le conteneur.
- **Journalisé** : quand une IP atteint le plafond, `logger.warning` avec l'IP. On distingue
  ainsi un festival bloqué d'une attaque.
- **Si l'IP est inconnue** (`get_client_ip` renvoie `None`, dev local), on ne compte pas.
- **Ce plafond ne protège pas les personnes**, c'est le rôle du plafond par email (§6). Il
  freine seulement un script naïf qui enverrait des codes à des milliers d'adresses depuis
  une seule IP, pour protéger la réputation de notre serveur mail. Un attaquant qui change
  d'IP le contourne. La vraie défense réseau (`limit_req` nginx, absent aujourd'hui) est
  hors chantier.

**Pourquoi D8 :** l'API v2 appelle `ReservationValidator` et `MembershipValidator` avec une
fausse requête anonyme (`api_v2/serializers.py:1410`, `1591`). Exiger la connexion dans les
validateurs casserait l'API, la caisse et une quarantaine de tests.

## 3. Les deux OTP du projet

Le projet a **deux** implémentations OTP. **Une seule est branchée.**

| | Onboarding | AuthBillet |
|---|---|---|
| Fichiers | `onboard/services.py` (`generate_otp`, `verify_otp`) | `AuthBillet/otp_service.py` + `otp_session.py` |
| Branché ? | **Oui, en production.** Appelé par `onboard/views.py:279` et `:1359`. Routes montées dans `TiBillet/urls_public.py:24` et `urls_tenants.py:92`. | **Non.** Aucun import hors des tests. |
| Où est gardé le code | Champs de `WaitingConfiguration` (schéma `meta`) | Au choix de l'appelant |
| Empreinte | PBKDF2 (`make_password`) | SHA-256 simple |
| Envoi du mail | Tâche Celery `onboard_otp_mailer` | Directement dans la requête (`mail.send()`, `otp_service.py:121`) |
| Tests | 19 | 33 |

**Pourquoi deux :** le service AuthBillet a été écrit le 2026-05-19 pour le wizard public de
proposition d'événement. Ce wizard est passé à la connexion classique deux jours plus tard
(`CHANGELOG/2026-05-21-wizard-evenement-v2-connexion-classique-lieu-pages.md`). Le service
n'a plus d'utilisateur depuis.

**Dans ce chantier :** on branche les fonctions pures d'`otp_service.py`. L'onboarding ne
bouge pas (sa migration = `OTP/CHANTIER-03`, hors périmètre). `OtpSession` est supprimée
(D11). Ses deux défauts :
- en DEBUG, **n'importe quel code à 6 chiffres est accepté** (`otp_session.py:95-100`). Pour
  une connexion, cela veut dire entrer dans n'importe quel compte ;
- son compteur d'essais vit dans la session. Il se remet à zéro si on change de cookie.

## 4. Parcours cibles

### 4.1 Se connecter (panneau `#loginPanel`)

1. La personne tape son email et clique « Recevoir un code ».
2. Le panneau se remplace par l'étape 2 : « Un code a été envoyé à `x@y.fr`. Il est valable
   10 minutes. Le code est au début de l'objet du mail. Pas reçu ? Regardez vos indésirables,
   ou demandez un nouveau code dans une minute. » Un champ « Code », un bouton « Me
   connecter », un bouton « Recevoir un nouveau code » et un lien « Changer d'adresse ».
3. Code juste : la personne est connectée. La page se recharge.

| Cas | Ce que voit la personne |
|---|---|
| Email mal écrit | Étape 1, message sous le champ |
| Nouveau code demandé moins de 60 s après le précédent | Étape 2 : « Un code vient de partir. Patientez une minute avant d'en demander un autre. » |
| Plafond par email ou par IP atteint | Étape 1 : « Trop de demandes. Réessayez un peu plus tard. » |
| Code faux | Étape 2 : « Code incorrect. Vérifiez le code reçu par mail. » |
| 5 codes faux | Étape 2 : « Trop d'essais. Demandez un nouveau code. » |
| Code expiré (plus de 10 minutes) ou déjà utilisé | Étape 2 : « Ce code a expiré. Demandez un nouveau code. » |
| Une réservation gratuite en attente ne peut plus être validée (événement complet) | Connexion réussie, avec en plus le message d'avertissement de `signals.py:263-269` |
| Déjà connecté, et envoie quand même l'étape 1 | Rechargement de la page, rien d'autre |
| Une autre personne était connectée sur ce navigateur | `login()` vide la session : la nouvelle personne est connectée |

### 4.2 Page de connexion pleine

`/login/login_fullpage/?next=<url signée>` reçoit deux appelants :
- `QrCodeScanPay.process_qrcode` (`views.py:2002-2008`), scanner « QR code scan & pay » ;
- `booking/views.py:805-808` (`cancel_confirm`), qui redirige **aujourd'hui** vers
  `/connexion/?next=` avec un `next` non signé. C'est déjà cassé (« Email validation
  error »). Il passe à `login_fullpage` avec `next=signing.dumps(request.get_full_path())`.

Mêmes deux étapes que le panneau. Après le code juste, la personne revient sur `next`.

### 4.3 Réserver un billet

- **Anonyme** : il voit les tarifs. Un seul bouton : « Se connecter pour réserver ». Il ouvre
  `#loginPanel`. Après le code juste, la page se recharge **avec le panneau de réservation
  ouvert** (`?openbookingPanel=true`, déjà géré par les 3 skins : classic, V2,
  faire_festival).
- **Connecté** : rien ne change (« Payer maintenant », « Ajouter au panier »).

**Pourquoi rouvrir le panneau :** Bootstrap n'ouvre qu'un panneau latéral à la fois. Cliquer
« Se connecter pour réserver » ferme donc `#bookingPanel`. Sans réouverture, la personne
doit, sur son téléphone, retrouver le bouton « Réserver » après la connexion.

### 4.4 Adhérer

Pareil : « Se connecter pour adhérer » pour un anonyme. Rien ne change pour un connecté.
Pas de paramètre d'ouverture automatique pour l'adhésion : après la connexion, la personne
rouvre le panneau (accepté).

### 4.5 Pages intégrées dans un autre site (`/event/embed/`, `/memberships/embed/`)

Dans une iframe d'un autre site, le cookie de session ne passe pas
(`SESSION_COOKIE_SAMESITE='Lax'`, `settings.py:100-101`). On ne peut donc pas se connecter
**dans** l'iframe. **À vérifier en S3 :** si ces pages affichent le bouton de connexion, le
remplacer par un lien vers la page de l'événement, dans un nouvel onglet
(`target="_blank"`).

## 5. Conception technique

### 5.1 Service `AuthBillet/connexion_par_code.py` (nouveau)

Trois fonctions. Elles ne connaissent ni la requête ni les gabarits.

```python
def cle_cache(email: str, suffixe: str) -> str:
    """Clé de cache d'un email. Sert au service ET au test E2E (§7.2)."""

def envoyer_un_code_de_connexion(email: str, adresse_ip: str | None) -> str:
    """
    Vérifie les plafonds, fabrique un code, garde son empreinte en cache,
    programme le mail.
    Renvoie "envoye", "attendre" (moins de 60 s) ou "trop_de_demandes".
    """

def verifier_le_code_de_connexion(email: str, code_saisi: str) -> str:
    """
    Renvoie "ok", "faux", "expire" ou "bloque".
    En cas de succès, efface le code : il ne sert qu'une fois.
    """
```

- **Email normalisé** avant tout usage : `email.strip().lower()`. (`get_or_create_user` ne
  fait que `.lower()`, `AuthBillet/utils.py:113`.)
- **Mode DEBUG** : `envoyer_un_code_de_connexion` écrit le code dans le journal
  (`logger.info`) juste avant de programmer le mail. C'est la seule fonction qui voit le
  code : ni la vue ni la tâche mail ne le journalisent.

**Clés du cache.** `django_tenants.cache.make_key` préfixe **automatiquement** chaque clé
par le nom du schéma (`KEY_FUNCTION`, `settings.py:321`). Un code demandé sur un lieu ne
marche donc que sur ce lieu. `<e>` = les 32 premiers caractères du SHA-256 de l'email :
memcached refuse les clés de plus de 250 caractères et certains caractères.

| Clé | Valeur | Durée | Rôle |
|---|---|---|---|
| `login_code:<e>:empreinte` | empreinte du code | 600 s | le code en cours |
| `login_code:<e>:essais` | compteur | 600 s | 5 essais au plus |
| `login_code:<e>:dernier_envoi` | `1` | 60 s | délai entre deux envois (`cache.add`, atomique) |
| `login_code:<e>:envois_de_l_heure` | compteur | 3600 s | 10 codes par heure et par email |
| `login_code_ip:<ip>:demandes_des_10_min` | compteur | 600 s | `CONNEXION_CODE_PLAFOND_IP_10_MIN` demandes par tranche de 10 minutes et par IP (D9) |

**Compteurs.** Ils doivent tenir face à deux requêtes arrivées en même temps.
- On crée le compteur avec `cache.add(cle, 0, timeout)`, puis on l'augmente avec
  `cache.incr(cle)`. Les deux opérations sont atomiques dans memcached.
- On décide **sur la valeur renvoyée par `incr`**, jamais sur un `get` suivi d'une
  comparaison. Pour les essais : `incr` **d'abord**, puis on compare à 5.
- Si `incr` lève `ValueError` (la clé a expiré entre `add` et `incr`) : `cache.add(cle, 1,
  timeout)` et on compte 1.

**Règles :**
- **Un nouveau code remplace l'ancien** : nouvelle empreinte, compteur d'essais remis à 0.
- **Empreinte** : `otp_service.hash_code_otp` (en `salted_hmac`, D10).
- **Adresse IP** : `AuthBillet.utils.get_client_ip` (`utils.py:13`). L'ordre de ses sources
  est un choix de sécurité documenté : ne pas le changer.

**Envoi du mail.** Nouvelle tâche Celery `code_de_connexion_celery_mailer(email, code,
langue)`, dans `BaseBillet/tasks.py`, à côté de `connexion_celery_mailer`.
- **Le lieu est transmis automatiquement** à la tâche (`TenantAwareCeleryApp`,
  `TiBillet/celery.py:14-17`).
- **Langue** : la vue passe `langue=get_language()` (celle de la personne) ; la tâche fait
  `activate(langue)`. Sans cela, gettext envoie le sujet en anglais (`tests/PIEGES.md`,
  P.ONBOARD.5).
- **Envoi** : la tâche appelle `otp_service.envoyer_email_otp(email, code,
  libelle_action=_("Connexion"), nom_organisation=config.organisation)`.
- **Mail pas parti** : `envoyer_email_otp` renvoie `mail.sended` (une ligne à ajouter). La
  tâche écrit une erreur (`logger.error`) si rien n'est parti. `CeleryMailerClass.send()`
  n'envoie rien, **sans erreur**, si la configuration mail est invalide (`tasks.py:107`).
- **Nouvelles tentatives courtes** : `max_retries=2`, `retry_backoff_max=60`. Ne pas copier
  les réglages de `connexion_celery_mailer` (6 tentatives, jusqu'à 600 s) : ils livreraient
  un code déjà expiré.
- Le code passe en clair par la file Celery, comme pour l'onboarding (`onboard/views.py:298`).

### 5.2 Vues

| Route | Vue | Rôle |
|---|---|---|
| `POST /connexion/` | `connexion` (réécrite) | Étape 1 : envoie le code, renvoie l'étape 2 |
| `GET /connexion/` | `connexion` | Requête htmx → partiel de l'étape 1 (lien « Changer d'adresse »). Sinon → redirection vers `/login/login_fullpage/` |
| `POST /connexion/code/` | `connexion_code` (nouvelle) | Étape 2 : vérifie le code, connecte |
| `GET /login/login_fullpage/` | `TiBilletLogin.login_fullpage` | Décode le `next` signé (`signing.loads`, signature fausse → pas de `next`). Passe le chemin obtenu au formulaire. **Son POST disparaît** : le formulaire poste sur `/connexion/` |

`connexion` et `connexion_code` sont des fonctions Django, comme `connexion` aujourd'hui.
Pas de throttle DRF : les plafonds sont dans le service (§5.1). Le slug `connexion` est
déjà réservé (`pages/models.py:48`) : `/connexion/code/` ne peut pas entrer en conflit avec
une page.

**Réponses htmx :**
- **Toujours répondre 200 avec le partiel**, le message d'erreur dedans. htmx ne remplace pas
  le contenu d'une réponse 4xx.
- **Jamais de `Http404` ni de `get_object_or_404`** dans ces deux vues : les 3 shells
  remplacent tout le `body` sur une réponse 404 ou 500 HTML (`classic/shell.html:194`,
  `V2/shell.html:200`, `faire_festival/shell.html:166`).

**`POST /connexion/`**
1. Déjà connecté → `HttpResponseClientRedirect(Referer)`.
2. `LoginEmailValidator` (`validators.py:187`). Invalide → étape 1 avec l'erreur.
3. `envoyer_un_code_de_connexion(email, get_client_ip(request))`.
4. `"envoye"` ou `"attendre"` → étape 2. `"trop_de_demandes"` → étape 1 avec le message.
5. **Ne crée ni compte ni portefeuille** (corrige A5).

**`POST /connexion/code/`**
1. Serializer : `email` (`EmailField`), `code` (`RegexField` `^\d{6}$`), `next` (facultatif).
2. `verifier_le_code_de_connexion(email, code)`. Tout sauf `"ok"` → étape 2 avec le message.
3. `"ok"` → finalisation, dans cet ordre :
   1. **Compte.** `user = get_or_create_user(email, send_mail=False)`. S'il renvoie `None`,
      le compte existe avec `email_error=True`. Or le code vient d'arriver : l'adresse
      marche. On remet `email_error=False`
      (`TibilletUser.objects.filter(email=email).update(email_error=False)`), puis on
      rappelle `get_or_create_user`.
   2. **Anciennes réservations (D12).**
      `Reservation.objects.filter(user_commande=user, status=Reservation.FREERES,
      event__datetime__lt=timezone.now()).update(status=Reservation.CANCELED)`. Un
      `.update()` ne passe pas par la machine à états : c'est voulu, `F` → annulée n'a pas
      de transition.
   3. **Activation.** `is_active=True`, `email_valid=True`, puis **`user.save()`**, pas un
      `.update()` : seul `save()` lance la machine à états. Elle valide les réservations `F`
      en attente sur ce lieu (`activator_free_reservation`).
   4. **Contrainte A8.** Ce `save()` peut lever `ValueError`. L'erreur part du `pre_save`,
      donc **avant** l'écriture en base. On l'attrape, on affiche son texte en
      avertissement, puis on rappelle `user.save()`. Au second passage, il ne reste aucune
      réservation `F` pour ce compte sur ce lieu : le premier passage les a toutes passées
      en `FA` ou annulées. Deux règles, **à écrire en commentaire dans le code** sinon
      quelqu'un les cassera :
      - **jamais de `transaction.atomic()`** autour de l'activation. Le second `save()`
        suppose que les réservations traitées au premier passage sont déjà écrites ;
      - **toujours l'instance `TibilletUser`** renvoyée par `get_or_create_user`, jamais un
        proxy (`HumanUser`, `SuperHumanUser`). Avec un proxy, `pre_save` part avec un autre
        nom de modèle et la machine à états ne se déclenche pas.
   5. **Portefeuille Fedow** s'il manque (même appel que `views.py:525-527`), dans un
      `try/except` qui journalise l'erreur **sans bloquer** : la connexion passe avant le
      portefeuille.
   6. **Connexion.** `login(request, user, backend="django.contrib.auth.backends.ModelBackend")`.
      Le projet n'a qu'un backend (aucun `AUTHENTICATION_BACKENDS` dans `settings.py`).
      L'écrire évite une erreur si on en ajoute un jour.
   7. **Redirection.** Message de succès, puis `HttpResponseClientRedirect(destination)` :
      - `next` présent et accepté par
        `url_has_allowed_host_and_scheme(next, allowed_hosts={request.get_host()})` →
        `next`. Refusé → `/`. `next` ne quitte jamais le site : pas besoin de le signer ;
      - sinon l'en-tête `Referer`, sauf s'il pointe sur `/login/` ;
      - sinon `/`.

### 5.3 Gabarits et JavaScript

**Connexion.**

| Fichier | Changement |
|---|---|
| `BaseBillet/templates/commun/formulaires/login.html` | Étape 1. `hx-post="/connexion/" hx-target="this" hx-swap="outerHTML"` (au lieu de `body`). Texte « un code vous sera envoyé par mail ». Champ caché `next`. Garder les id `loginForm` et `loginEmail` (`tests/e2e/test_login.py`). Supprimer le JS mort (l.25-54). |
| `BaseBillet/templates/commun/formulaires/login_code.html` | **Nouveau.** Étape 2 (détail sous ce tableau). |
| `BaseBillet/templates/commun/offcanvas/connexion.html` | Petit script : à l'ouverture de `#loginPanel`, copier le `data-next` du bouton qui l'a ouvert (`event.relatedTarget`) dans le champ caché `next` du formulaire. |
| `BaseBillet/templates/fonctionnel/connexion/partials/fullpage_inner.html` | **Inclut** `commun/formulaires/login.html` (avec `next`) au lieu d'avoir son propre formulaire. Un seul formulaire, un seul partiel d'étape 2 pour le panneau et la page pleine. Le `/` en trop après la query string (l.14) disparaît avec. |
| `fonctionnel/connexion/partials/confirmation_inner.html` et `fonctionnel/connexion/confirmation.html` | **Supprimés** (« vérifiez vos mails »). `confirmation.html` n'est déjà rendu par aucune vue. |
| `BaseBillet/templates/htmx/components/panier_scripts.html` (l.118) | Le 403 ouvre `#loginPanel` seulement pour `/panier/`. Étendre le test à `/event/` et `/memberships/` : une session expirée dans un onglet resté ouvert doit ouvrir la connexion, pas rien. |

**`login_code.html` :**
- champs cachés `email` et `next` ;
- champ `code` : `type="text"`, `inputmode="numeric"`, `autocomplete="one-time-code"`,
  `pattern="\d{6}"`, `maxlength="6"`, `autofocus`, avec un `<label>` ;
- bouton « Me connecter » : `hx-post="/connexion/code/"` ;
- bouton « Recevoir un nouveau code » : `hx-post="/connexion/"`, avec le même `email` caché ;
- lien « Changer d'adresse » : `hx-get="/connexion/?next=..."` ;
- tous : `hx-target="closest form" hx-swap="outerHTML"` ;
- accessibilité : `role="alert"` sur les messages d'erreur seulement. Le texte « code
  envoyé » n'a pas d'attribut ARIA.

**Réservation et adhésion.**

| Fichier | Changement |
|---|---|
| `BaseBillet/templates/commun/formulaires/reservation.html` | Remplacer **tout** le bloc `{% if user.is_anonymous %}…{% endif %}` (l.20-86) par le champ email en lecture seule, entouré de `{% if user.is_authenticated %}`. La branche « email non confirmé » disparaît avec : c'est du code mort, car un compte non activé est vu comme anonyme (le `ModelBackend` le refuse). Remplacer le contenu du `{% else %}` anonyme des boutons (l.608-626) par **un** bouton « Se connecter pour réserver » : `data-bs-toggle="offcanvas"`, `data-bs-target="#loginPanel"`, `data-next="{{ request.path }}?openbookingPanel=true"`, `data-testid="booking-login"`. |
| `BaseBillet/templates/commun/adhesion/form.html` | Pareil : le bloc l.198-270 devient le champ en lecture seule sous `{% if user.is_authenticated %}`. Le contenu du `{% else %}` des boutons (l.691-707) devient **un** bouton « Se connecter pour adhérer » (`data-testid="membership-login"`, sans `data-next`). |
| `BaseBillet/static/commun/js/booking-calculator.mjs` | Supprimer le contrôle email / confirmation (l.72-104). |
| `BaseBillet/static/commun/js/membership-form.mjs` | Supprimer l.7-23 (`emailInput`, `confirmInput`, `errorDiv`, `validateEmails`). Dans `validateAll`, retirer `const okEmails = validateEmails();` (l.77) et `okEmails && ` (l.80). Supprimer l.95-98. **Garder** l.83-93 (groupes de cases obligatoires). |
| `BaseBillet/templates/fonctionnel/event/reservation_ok.html` | **Supprimé** (« validez votre email »). |

**Attention, `membership-form.mjs`.** Il est chargé dans le même `<script type="module">`
que le changement de thème, de langue et `bs-counter` (`classic/shell.html:211-221`,
`V2/shell.html:219`, `faire_festival/shell.html:208`). Une erreur de syntaxe dans ce fichier
casse ces modules **sur tout le site**, y compris les compteurs de quantité de la
réservation. Suivre les lignes ci-dessus exactement.

**Règles communes :**
- Les copies de `www/static/` viennent de `collectstatic` : ne jamais les modifier à la main.
- `data-testid` des nouveaux éléments : `login-email`, `login-submit`, `login-code`,
  `login-code-submit`, `login-code-resend`, `login-change-email`, `booking-login`,
  `membership-login`.
- Textes nouveaux : `msgid` en **français**. Ne pas lancer `makemessages` ; le signaler au
  mainteneur en fin de chantier.

### 5.4 Réservation (`EventMVT`)

- **`get_permissions()` par liste blanche** :
  `if self.action in ['reservation', 'action_reservation']` → `IsAuthenticated`, sinon
  `AllowAny`.
  - Ne pas raisonner sur la méthode HTTP : `partial_list` est un **POST public** (filtres).
  - Retirer le `permission_classes` de l'`@action` d'`action_reservation` : c'est
    `get_permissions()` qui décide (corrige A7).
  - Même modèle que `PanierMVT.get_permissions()` (`views.py:5598-5606`).
- **`reservation()`** : `donnees = request.data.copy()`, puis
  `donnees["email"] = request.user.email`.
  - C'est `IsAuthenticated` qui corrige A1 et A2. L'injection change seulement le résultat
    pour une personne connectée : elle réserve pour elle-même, au lieu de recevoir une
    erreur si l'email posté diffère (par exemple une autre casse).
  - `.copy()` garde les listes : `extract_products` lit la copie avec `getlist`. Les champs
    `form__*` sont relus sur `request.data`, l'original (`validators.py:854`), qui contient
    les mêmes clés. Seul `email` diffère entre les deux.
- Supprimer la branche « compte non activé » et le rendu de `reservation_ok.html`
  (`views.py:3334-3348`). Une réservation gratuite finit toujours sur « Réservation
  validée ! » et la redirection vers `my_account-my-reservations`.
- `stripe_return` : inchangé.

### 5.5 Adhésion (`MembershipMVT`)

- `get_permissions()` (`views.py:4615`) : ajouter `create` → `IsAuthenticated`. Aucune autre
  action n'accepte d'adhésion anonyme.
- `create()` : même injection de `request.user.email` (les champs `form__*` sont relus sur
  `request.data`, `validators.py:1080`).
- `MembershipValidator` : inchangé (D8).

### 5.6 Ce qui ne change pas

| Élément | Pourquoi il reste |
|---|---|
| `ReservationValidator`, `MembershipValidator`, `TicketCreator` | API v2, caisse, admin (D8) |
| `get_or_create_user`, `connexion_celery_mailer`, `emails/connexion.html` | Appelés par l'API v2 (nouveaux comptes), la liaison de carte QR, `resend_activation_email` et l'admin |
| `/emailconfirmation/` et `AuthBillet.views.activate` | D3. Usages : SSO entre lieux (`views.py:861-919`), `go_admin`, `connect_to`, `login_as_user`, commande `get_login_link`, onboarding (`onboard/views.py:467`, `onboard/tasks.py:159-163`), 3 mails (`tasks.py:460`, `581`, `700`) |
| `MyAccount.resend_activation_email` (`views.py:1436`) | Les comptes liés par carte QR sont connectés avec `email_valid=False` (`views.py:622`, `676-677`). Ils peuvent aussi valider leur email en se déconnectant puis en se connectant par code ; ce bouton reste la voie sans déconnexion |
| Statut `F` et `activator_free_reservation` | L'API v2 crée encore des réservations `F` pour des comptes non activés. La 1re connexion par code les valide (§5.2) |
| `ScanQrCode` (dont son lien « TEST MODE ») | D2 |
| OTP de l'onboarding | Hors périmètre (`OTP/CHANTIER-03`) |

### 5.7 Données existantes

**Aucune migration.**
- Les comptes non activés (anciennes réservations anonymes, API, caisse) le deviennent à
  leur première connexion par code.
- Leurs réservations `F` en attente sur ce lieu sont traitées au passage : annulées si
  l'événement est passé (D12), sinon validées si la jauge le permet.
- Les sessions déjà ouvertes restent valides (`SESSION_COOKIE_AGE` = 12 semaines).

## 6. Limites et sécurité

| Règle | Valeur | D'où |
|---|---|---|
| Durée de vie d'un code | 10 minutes | `OTP_TTL_SECONDS` |
| Essais par code | 5 | `OTP_MAX_ATTEMPTS` |
| Délai entre deux envois au même email | 60 s | `OTP_RESEND_COOLDOWN_SECONDS` |
| Codes par heure et par email | 10 | nouveau. 10 plutôt que 5 : quelqu'un dont le mail arrive dans les indésirables reclique plusieurs fois |
| Demandes de code par IP | 500 par tranche de 10 minutes, réglable | D9 |
| Usage unique | clés effacées après un succès | §5.1 |
| Portée | un code ne marche que sur le lieu qui l'a envoyé | `make_key` |
| DEBUG | code dans le journal serveur, aucun code universel | D7 |

- **Deviner un code** : 10 codes par heure × 5 essais = 50 essais par heure et par compte,
  soit environ 1 chance sur 20 000 par heure.
- **Savoir si un compte existe** : impossible par ce formulaire. La réponse de l'étape 1 est
  la même dans tous les cas ; le compte n'est créé qu'après le bon code.
- **Bloquer quelqu'un d'autre** : possible. Qui connaît un email peut épuiser ses codes de
  l'heure, ou les essais du code en cours. L'effet dure au plus une heure, et aucune donnée
  n'est exposée. **Risque accepté.**
- **Pas de plafond par IP sur la vérification.** Avec des IP qui changent, on peut tenter
  50 codes par heure sur **chacun** de plusieurs comptes. Risque accepté : la probabilité
  par compte reste celle de la première ligne.

## 7. Tests

**Règles :**
- **Vérification par mutation** : chaque nouveau test doit être vu **échouer** sur une
  modification volontaire du code avant d'être livré.
- Lancer les tests : skill `tibillet-test`, `make test` et `make e2e`.
- Citer les tests par **nom de fonction**, pas par numéro de ligne : les lignes bougent.

### 7.1 Nouveaux tests pytest

- **Service** :
  - le code est gardé en cache et le mail programmé ;
  - le délai de 60 s ;
  - le plafond par email ;
  - le plafond par IP, avec une petite valeur posée par `override_settings`
    (`CONNEXION_CODE_PLAFOND_IP_10_MIN`) ; le `logger.warning` quand il est atteint ;
    une IP `None` n'est pas comptée ;
  - la vérification : `ok`, `faux`, `expire`, `bloque` ;
  - l'usage unique ;
  - un nouveau code remplace l'ancien ;
  - un code d'un lieu est refusé sur un autre lieu.
- **Vues de connexion** :
  - `POST /connexion/` ne crée **ni compte ni portefeuille** (A5) ;
  - le bon code crée un compte activé et connecté ;
  - le bon code valide une réservation `F` en attente ;
  - le bon code annule une réservation `F` d'un événement passé (D12) ;
  - le cas A8 (événement devenu complet) connecte quand même ;
  - un `next` relatif redirige ; un `next` vers un autre domaine renvoie sur `/` ;
  - un compte avec `email_error=True` se connecte ;
  - Fedow en panne : la connexion réussit quand même.
- **Réservation et adhésion** :
  - anonyme → 403, pour `reservation`, `action_reservation` (A7) et `memberships/create` ;
  - `partial_list` (POST) reste public ;
  - un connecté qui poste l'email d'un autre réserve **pour lui-même** ;
  - un tarif réservé aux adhérents est refusé à un connecté non adhérent (A2).
- **Pièges :**
  - **Isoler le cache sans le vider.** Un email unique par test
    (`f"code-{uuid4().hex[:8]}@test.local"`) et une IP unique par test (`REMOTE_ADDR`). En
    fin de test, `cache.delete_many([...])` des clés de cet email et de cette IP, dans le
    contexte du lieu. **Jamais `cache.clear()`** : sur memcached c'est un `flush_all`, tous
    lieux confondus, et le serveur de dev partage ce memcached (`tests/PIEGES.md`, section
    « Ne PAS utiliser `cache.clear()` »).
  - **Patcher les tâches Celery.** Sous `django_db`, `on_commit` ne part pas (PIEGES 13.1).
    Mais un `.delay()` direct part vers le **vrai** broker : le projet n'a pas de
    `task_always_eager`. Patcher la tâche mail du code **et**
    `BaseBillet.signals.ticket_celery_mailer` et `webhook_reservation`, appelées par
    `reservation_paid` (`signals.py:171`, `:188`) quand une réservation `F` est validée.
  - Citer les pièges de `PIEGES.md` par **titre** : les numéros 9.98 et 9.99 existent deux
    fois.

### 7.2 Nouveau test E2E : connexion par code

Un test E2E ne peut pas lire le mail. Il procède ainsi :
1. il demande un code par le panneau ;
2. via `django_shell`, **dans le contexte du lieu**, il remplace l'empreinte en cache par
   celle d'un code connu. La clé est construite en important `cle_cache` du service
   (jamais recopiée à la main). Écrire le snippet avec des guillemets **simples** :
   `django_shell` n'échappe que les doubles ;
3. il tape ce code et vérifie qu'il est connecté ;
4. variante réservation : depuis le bouton « Se connecter pour réserver », il vérifie que le
   panneau de réservation est rouvert après la connexion.

Le reste de la suite continue de se connecter par `login_as` (`__test_only__/force_login/`).

### 7.3 Tests existants à reprendre

| Fichier | Tests | Action |
|---|---|---|
| `tests/pytest/test_parite_avec_sans_panier.py` | `test_p2bis_billet_payant_a_zero_euro_pour_un_visiteur_anonyme`, `test_deux_reservations_gratuites_d_un_visiteur_non_active_attendent_l_activation` | Supprimer |
| idem | `test_une_reservation_gratuite_confirmee_apres_20_minutes_reste_valide` | Réécrire : créer la réservation `F` par l'API v2, puis activer le compte |
| idem | docstring du module (l.19-22) | Retirer le « périmètre anonyme ». Les helpers `reserver_des_billets` et `adherer` reçoivent déjà un client connecté : rien à changer |
| `tests/pytest/test_stripe_membership_simple.py` | `test_anonymous_membership_paid`, `test_anonymous_membership_dynamic_form`, `test_membership_free_price`, `test_ssa_membership_tokens` | Client connecté |
| `tests/pytest/test_stripe_membership_complex.py` | les 6 tests qui passent par `_submit_membership` | Client connecté |
| `tests/e2e/test_reservation_validations.py` | `test_booking_form_validation_errors` | `login_as` ; supprimer l'étape 5 (confirmation d'email) |
| `tests/e2e/test_stripe_smoke.py` | `test_smoke_membership_stripe_checkout`, `test_smoke_booking_stripe_checkout` | `login_as` |
| `tests/e2e/test_numeric_overflow_validation.py` | `test_membership_rejects_oversized_custom_amount`, `test_booking_rejects_oversized_custom_amount` | `login_as` |
| `tests/e2e/test_reservation_limits.py` | `test_stock_max_and_membership_messages`, étapes 3 et 6 | Revoir l'affichage anonyme |
| `tests/e2e/test_membership_validations.py` | `test_membership_form_validation_errors` | `login_as` ; supprimer le contrôle de confirmation |
| `tests/e2e/test_membership_free_price_multi.py` | les 4 scénarios (helper `_remplir_formulaire_base`) | `login_as` |
| `tests/e2e/test_membership_dynamic_form_full_cycle.py` | `test_step2_public_subscribes_with_dynamic_form` et les étapes suivantes | `login_as` |
| `tests/e2e/test_membership_manual_validation.py` | `test_request_and_approve_membership` | `login_as` |
| `tests/e2e/test_login.py` | `test_should_validate_email_format` | Inchangé si les id `loginForm` / `loginEmail` restent (§5.3) |
| `tests/e2e/test_panier_flow.py` | `test_e2_un_anonyme_qui_veut_ajouter_au_panier_voit_le_panneau_de_connexion` | Le bouton devient `booking-login` |

**Inchangés (vérifiés) :**
- `test_reservation_subevent_tickets.py` : il appelle `ReservationValidator` directement, et
  D8 ne le change pas ;
- `test_qrcodescanpay_flux_complet.py` : il vérifie seulement la redirection vers
  `/login/login_fullpage` avec `next=` ;
- `test_management_commands.py::test_get_login_link` : le lien magique reste (D3) ;
- les tests de l'API v2 : ils passent par les validateurs, que D8 ne change pas.

Lancer quand même la **suite complète**, pas seulement le domaine touché.

## 8. Découpage en sessions

| Session | Contenu | Fin de session |
|---|---|---|
| S1 | Service `connexion_par_code.py`, réglage `CONNEXION_CODE_PLAFOND_IP_10_MIN` (`settings.py` + `env_example`), tâche mail, empreinte (D10), tests du service | Tests du service verts |
| S2 | Vues `/connexion/` et `/connexion/code/`, `login_fullpage`, `booking/views.py:806`, gabarits de connexion, script `data-next`, tests des vues, E2E de connexion | Connexion par code utilisable ; suite verte |
| S3 | Réservation et adhésion réservées aux connectés : permissions, injection de l'email, gabarits, JS, `panier_scripts.html`, iframes (§4.5), **et reprise des tests qu'elles cassent** (§7.3) | `make test` et `make e2e` verts |
| S4 | Suppression d'`OtpSession` (D11). `CHANGELOG/`. Mise à jour de `OTP/INDEX.md`. Ajouts à `tests/PIEGES.md` (liste ci-dessous). Chaînes i18n signalées | Docs à jour |

À ajouter ou corriger dans `tests/PIEGES.md` :
- un compte non activé est vu comme anonyme ;
- un `get_permissions()` écrit en dur écrase le `permission_classes` des `@action` (A7) ;
- un `ValueError` levé dans un `pre_save` annule le `save()` (A8) ;
- corriger « le projet a plusieurs backends » (entrée « force_login(term_user) ne pose PAS
  set_expiry ») : il n'en a qu'un. Même correction dans le commentaire de
  `onboard/views.py:395`.

`OTP/INDEX.md` est périmé : il dit `step0_verify` encore en place, et propose `OtpSession`.

## 9. C'est fini quand

- `make test` et `make e2e` sont verts.
- Un anonyme ne voit que « Se connecter pour réserver » ou « Se connecter pour adhérer ».
- `POST /connexion/` n'écrit rien en base.
- Une connexion par code réussit sur le lieu de démo, avec le code lu dans le journal (DEBUG).
- Après une connexion depuis le formulaire de réservation, le panneau de réservation est
  rouvert.
- `CHANGELOG/` est écrit, `OTP/INDEX.md` et `tests/PIEGES.md` sont à jour.
- Les nouvelles chaînes à traduire sont signalées au mainteneur.

## 10. Hors périmètre

- Liaison d'une carte QR (D2).
- Remplacer le lien magique, SSO entre lieux (D3).
- Migrer l'OTP de l'onboarding (`OTP/CHANTIER-03`).
- Proposition d'événement anonyme (`EventWizard`, `proposition_anonyme_autorisee`).
- Corriger A8 à la source : `activator_free_reservation` ne devrait pas lever d'erreur dans
  un `pre_save`. Ce chantier le **contourne** (§5.2), sans le corriger. Deuxième site
  concerné, non traité : `ScanQrCode.retrieve` fait `user.is_active = True; user.save()` sans
  attraper l'erreur (`views.py:622-623`, D2).
- Une réservation `F` reste bloquée si le compte est activé depuis **un autre** lieu
  (`signals.py:233-238`).
- L'API v1 `ApiReservationViewset.create` est encore en `AllowAny`
  (`ApiBillet/views.py:515-517`). C'est une réservation anonyme résiduelle, qui plante déjà
  (`self.user_commande` jamais posé, `ApiBillet/serializers.py:1142`).
- La route cassée `/api/user/activate/<uid>/<token>` (`AuthBillet/urls.py:31`).
- Un plafond réseau (`limit_req` nginx).
- Rouvrir automatiquement le panneau d'adhésion après la connexion.
