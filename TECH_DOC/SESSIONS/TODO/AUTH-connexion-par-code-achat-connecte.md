# AUTH — Connexion par code à 6 chiffres, guichet commun à tous les lieux, achat réservé aux personnes connectées

> **Status :** spec du 2026-09-22, **révisée le 2026-10-19**. **Réalisée (S1 à S5) le
> 2026-10-20, non commitée.** Deux décisions attendent le mainteneur (§12). Suivi :
> `CHANGELOG/2026-10-20-auth-guichet-connexion-par-code.md`.
> - 2026-09-22 : relue par un agent Opus (exactitude face au code) et un agent Fable (point de
>   vue du mainteneur). Leurs corrections sont intégrées.
> - 2026-10-19 : ajout du **guichet de connexion commun** (SSO entre lieux, D13-D16), de la
>   **déconnexion de partout** (D14), de la **validation immédiate des réservations gratuites**
>   (D15). Numéros de ligne remis à jour face au code du 2026-10-19. Relue le même jour par
>   un agent Fable : ses corrections sont intégrées (A8 corrigé dans le code depuis le
>   2026-10-11, plafonds comptés sur le guichet, alias de cache `verrous`, domaine du lieu
>   par `request.tenant.domain_url`, déconnexion depuis l'admin, comptes non humains).
>
> **Pré-requis :** aucun.
> **Origine :** audit de la réservation anonyme (2026-09-22).
> **Remplace :** l'idée « CHANTIER-02 — Login OTP » du hub `TECH_DOC/SESSIONS/OTP/INDEX.md`.
> **Décisions :** toutes tranchées par le mainteneur (§2).
> **Numéros de ligne :** relevés le 2026-10-19. Ils bougent vite (`BaseBillet/views.py` a pris
> ~700 lignes en un mois) : toujours relocaliser par `rg` le nom de la fonction citée.

## Lexique

| Terme | Sens |
|---|---|
| Code | code à 6 chiffres envoyé par mail, à taper sur le guichet (OTP) |
| Empreinte | le code passé dans une fonction à sens unique (`hash_code_otp`). On garde l'empreinte, jamais le code |
| Guichet | la page de connexion commune à tous les lieux. Elle vit sur le domaine du schéma `public` (`tibillet.coop` en production, `tibillet.localhost` en dev) |
| Ticket | preuve de connexion que le guichet donne au lieu : signée, valable 60 secondes, pour un seul lieu, une seule fois |
| Jeton de session | champ du compte qui entre dans l'empreinte de toutes ses sessions. Le changer déconnecte la personne de partout |
| Lien magique | lien `/emailconfirmation/<jeton>` envoyé par mail : un clic connecte |
| Compte activé | `is_active=True` et `email_valid=True` |
| Anonyme | visiteur non connecté |
| Réservation `F` / `FA` | réservation gratuite, compte pas encore activé / compte activé |
| Machine à états | `BaseBillet/signals.py` : un `pre_save` qui réagit aux changements de statut. Pour un compte : le passage `is_active` False → True |
| Rattachement | la liste des lieux d'un compte (`TibilletUser.client_achat`) |
| Jauge | nombre de places d'un événement (`jauge_max`) |
| Plafond | nombre maximum de demandes permises dans un temps donné |
| Partiel | morceau de HTML renvoyé à htmx, qui remplace une zone de la page |
| Lieu | un tenant (un schéma PostgreSQL) |

## 1. Pourquoi ce chantier

Aujourd'hui, un anonyme peut réserver un billet ou adhérer. Il tape un email dans le
formulaire. Le site crée un compte non activé à cet email et envoie un lien magique.

- **Billet gratuit** : la réservation reste en `F`. Le clic sur le lien active le compte.
  La machine à états (`signals.py:503`) lance `activator_free_reservation`
  (`signals.py:320`), qui passe la réservation en `FA` et envoie les billets.
- **Billet payant** : Stripe valide le paiement. L'état du compte n'est jamais regardé.
- **Adhésion** : même principe (`MembershipValidator`).

Ce mécanisme a des failles. Les deux relectures les ont confirmées dans le code ; aucune
n'est encore prouvée par un test.

| # | Constat | Où |
|---|---|---|
| A1 | **Un anonyme peut réserver au nom d'un autre.** Il tape l'email d'un compte activé : la réservation gratuite passe en `FA` tout de suite, les billets partent chez cette personne. Cela prend son quota par personne et des places dans la jauge. (Une personne connectée est déjà protégée : `validate_email`, `validators.py:755-763`.) | `ReservationValidator.validate_email`, `TicketCreator.__init__` |
| A2 | **Tarif réservé aux adhérents** : pour un anonyme, le serveur vérifie l'adhésion de l'email *tapé*. Seul le gabarit cache le tarif. | `ReservationValidator` (contrôle d'adhésion) |
| A3 | Une adhésion à 0 € est validée tout de suite pour n'importe quel email. `MembershipValidator` ne compare jamais l'email tapé à celui de la personne connectée. | `MembershipValidator` |
| A4 | Aucun plafond de requêtes sur `/connexion/`, la réservation et l'adhésion (`DEFAULT_THROTTLE_CLASSES` est commenté, `settings.py:515`). On peut inonder une boîte mail. Des réservations gratuites fantômes bloquent la jauge 30 minutes. | `connexion` (`views.py:586`), `EventMVT.reservation`, `MembershipMVT.create` |
| A5 | `/connexion/` crée le compte et le portefeuille Fedow **avant** toute preuve de l'email. Elle plante (500) si le compte a `email_error=True` : `get_or_create_user` renvoie `None`, puis `user.wallet`. | `views.py:592-595`, `AuthBillet/utils.py:143-145` |
| A6 | Le lien magique marche 72 heures, et plusieurs fois. | `AuthBillet/views.py:135` |
| A7 | `EventMVT.get_permissions()` (`views.py:3316`) renvoie `AllowAny` pour toutes les actions sauf `admin_show_event_detail`. Le `permission_classes=[IsAuthenticated]` posé sur l'`@action` `action_reservation` (`views.py:4037`) est donc ignoré (DRF ne le lit que dans le `get_permissions()` par défaut). Un anonyme l'atteint et obtient une 500. | `views.py:3316-3327`, `4037` |
| A8 | **Corrigé dans le code le 2026-10-11** (commit 4309741c). Quand une ancienne réservation gratuite ne peut plus être validée (événement complet), `activator_free_reservation` ne lève plus d'erreur : il pose le texte sur `user.message_reservation_annulee`, et `activate()` l'affiche après `user.save()`. **Reste à faire dans ce chantier :** transporter ce message du guichet jusqu'au lieu (champ `avertissement` du ticket, §3.3). | `signals.py:366-373`, `AuthBillet/views.py:146-154` |
| A9 | **Une connexion par lieu.** Une personne connectée sur le lieu A doit refaire toute la procédure sur le lieu B : le cookie de session est attaché au domaine (`SESSION_COOKIE_DOMAIN` désactivé, `settings.py:107`). | `settings.py:80-107` |

**Le but :**
- une seule façon d'acheter sur le site : être connecté ;
- une seule façon de se connecter : un code reçu par mail, tapé sur le **guichet commun** ;
- **une seule connexion pour tous les lieux** : sur le 2ᵉ lieu, un clic suffit.

Le reste du site exige déjà la connexion : panier, réservation de ressource (`booking`),
financement participatif (`crowds`).

## 2. Décisions

### 2.1 Tranchées par le mainteneur

| # | Sujet | Décision |
|---|---|---|
| D1 | Adhésion anonyme | **Retirée**, comme la réservation anonyme. |
| D2 | Liaison d'une carte QR (`/qr/link/`) | **Hors chantier, inchangée.** Scan du QR → email → compte créé et connecté. Un autre chantier plus tard. |
| D3 | Lien magique | **Gardé pour l'instant** (liste de ses usages au §5.10). Ce chantier arrête seulement de l'envoyer pour se connecter. |
| D4 | Où garder le code | **Cache Django.** Attention : c'est **memcached** (`TiBillet/settings.py:317-325`), pas Redis. Les commentaires de l'onboarding disent « Redis » à tort. |
| D13 | Connexion entre lieux (SSO) | **Fait maison**, par un **guichet** sur le domaine du schéma `public`. Pas de Keycloak : un service de plus à faire tourner, des comptes à synchroniser, un habillage par lieu. Tous les lieux partagent déjà le même Django et la même table de comptes (`AuthBillet` est dans les `SHARED_APPS`). Détail au §3. |
| D14 | Déconnexion | **De partout.** « Me déconnecter » sur un lieu ferme toutes les sessions de la personne : tous les lieux et le guichet. Détail au §5.6. |
| D15 | Réservation gratuite d'un compte non activé | **Validée tout de suite (`FA`)**, plus jamais en attente (`F`). Les validateurs ne posent plus `F`. Détail au §5.7. |

### 2.2 Proposées par la spec, validées par le mainteneur

| # | Sujet | Proposition |
|---|---|---|
| D5 | Quel service OTP | Les **fonctions pures** de `AuthBillet/otp_service.py`. Pas `OtpSession` : elle range tout en session (voir §4). |
| D6 | Saisie du code | **Un seul champ**, pas 6 cases. Sur iOS, l'app Mail propose le code reçu (`autocomplete="one-time-code"`). Ailleurs, on tape 6 chiffres. Aucun JavaScript. |
| D7 | Mode DEBUG | Le code est écrit dans le journal du serveur. **Aucun code universel.** |
| D8 | API v2, caisse, admin | **Inchangés, sauf D15.** Les validateurs gardent leur champ `email`. La connexion est exigée dans les **vues du site**, pas dans les validateurs. |
| D9 | Plafond par adresse IP | **500 demandes de code par tranche de 10 minutes** (environ 3 000 par heure), réglable sans toucher au code. Détail ci-dessous. |
| D10 | Empreinte du code | `hash_code_otp` passe en `salted_hmac("AuthBillet.otp", code, algorithm="sha256").hexdigest()`. Avec un SHA-256 simple, une copie du cache suffit pour retrouver le code : il n'y a qu'un million de codes possibles. Avec la clé secrète du projet, c'est impossible. Une ligne ; `test_otp_service.py` reste valable (64 caractères hexadécimaux). |
| D11 | `OtpSession` | **Supprimée** avec ses 15 tests (`otp_session.py`, `test_otp_session.py`). Aucun utilisateur, et un raccourci DEBUG qui ouvrirait n'importe quel compte. |
| D12 | Anciennes réservations `F` d'événements passés | **Annulées** juste avant l'activation du compte (§5.4). Sinon, la 1re connexion enverrait les billets d'événements terminés : l'activateur ne regarde pas la date. Après D15, seules les `F` **déjà en base** sont concernées. Inutile quand le compte est déjà activé : l'activateur ne tournera pas |
| D16 | Rattachement au lieu | À chaque connexion sur un lieu, le lieu est ajouté à la liste des lieux du compte (`client_achat`). Sinon, avec le guichet, le lieu ne verrait jamais la personne dans son admin (§5.5). |

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
- **Compté sur le guichet, tous lieux confondus** (§3.4). Compté par lieu, il serait
  multiplié par le nombre de lieux (~500 en production).
- **Ce plafond ne protège pas les personnes**, c'est le rôle du plafond par email (§7). Il
  freine seulement un script naïf qui enverrait des codes à des milliers d'adresses depuis
  une seule IP, pour protéger la réputation de notre serveur mail. Un attaquant qui change
  d'IP le contourne. La vraie défense réseau (`limit_req` nginx, absent aujourd'hui) est
  hors chantier. Keycloak fait le même choix : il n'a aucune limite par IP.

**Pourquoi D8 :** l'API v2 appelle `ReservationValidator` et `MembershipValidator` avec une
fausse requête anonyme (`api_v2/serializers.py:1580`, `1596`). Exiger la connexion dans les
validateurs casserait l'API, la caisse et une quarantaine de tests.

**Pourquoi D15 :** après ce chantier, une personne connectée a **toujours** un compte activé
(le `ModelBackend` refuse une session à un compte non activé). Le statut `F` ne viendrait
donc plus que de l'API v2, qui réserve pour un email. La clé API appartient au lieu : on lui
fait confiance, comme quand le lieu saisit une réservation dans l'admin. Garder `F` aurait
un coût : une réservation `F` n'est validée que quand le compte **passe** de « non activé »
à « activé », et seulement sur le lieu où ça se passe. Une personne qui s'est d'abord
connectée sur un autre lieu garderait sa réservation en attente pour toujours.
**Contrepartie acceptée :** les billets d'une réservation gratuite faite par l'API partent à
un email jamais vérifié.

## 3. Le guichet commun (SSO entre lieux)

### 3.1 Pourquoi un guichet

Chaque lieu a son propre domaine (`lespass.tibillet.coop`, ou un domaine personnalisé comme
`monfestival.fr`). Le cookie de session reste attaché à ce domaine. Le lieu B ne peut donc
pas savoir que la personne est connectée sur le lieu A.

| Raccourci écarté | Pourquoi |
|---|---|
| Cookie partagé entre sous-domaines (`SESSION_COOKIE_DOMAIN`) | Une seule session pour tous les lieux : risque de vol de session entre sous-domaines (avertissement de `settings.py:103-106`). Et ne marche pas avec les domaines personnalisés |
| Demander « es-tu connecté ? » en arrière-plan (iframe, fetch) | Safari et Chrome bloquent les cookies tiers |
| Keycloak | D13 |

**La seule voie fiable est la redirection de page entière.** Lors d'une navigation, le
navigateur envoie le cookie du domaine visité, même avec `SameSite=Lax`.

### 3.2 Le parcours

```
Lieu B : clic « Se connecter »
   │  GET /connexion/?next=<page>  →  B garde `state` et `next` dans sa session
   │  redirection vers https://<guichet>/sso/?lieu=<domaine de B>&state=<state>
   ▼
Guichet : la personne est-elle connectée sur le guichet ?
   ├─ OUI → rien à taper ───────────────────────────────┐
   └─ NON → email → code à 6 chiffres → compte activé   │
            → connexion sur le guichet                  │
                                                        ▼
   redirection vers https://<domaine de B>/connexion/retour/?ticket=<ticket>&state=<state>
   ▼
Lieu B : vérifie state et ticket → rattache le lieu → login() → redirection vers `next`
```

- **1er lieu visité** : la personne tape le code une fois, sur le guichet.
- **Lieux suivants** : un clic sur « Se connecter », deux redirections invisibles, et elle
  est connectée.
- **Le contrôle se fait au clic** sur « Se connecter », jamais à chaque page. Un aller-retour
  vers le guichet pour chaque visiteur anonyme ralentirait le site et gênerait les robots des
  moteurs de recherche.

### 3.3 Le ticket

Le ticket est une chaîne signée par `django.core.signing`, avec le sel
`"AuthBillet.sso.ticket"`. Il contient :

| Clé | Valeur |
|---|---|
| `compte` | `str(user.pk)` (UUID) |
| `lieu` | le domaine du lieu de destination, tel que reçu dans `lieu=` |
| `unique` | `secrets.token_hex(16)` |
| `avertissement` | facultatif : le texte de `user.message_reservation_annulee` (A8, §5.4), à afficher sur le lieu |

**Le domaine du lieu, c'est `request.tenant.domain_url`, jamais `request.get_host()`.** Le
middleware de django-tenants retire le port et le `www.` avant de chercher le `Domain`
(`django_tenants/middleware/main.py:22-30`), puis pose `request.tenant.domain_url`.
`get_host()` garde le port : en dev, `lespass.tibillet.localhost:8080` est accepté
(`settings.py:150`) mais n'est pas une ligne `Domain`. Le lieu envoie donc
`lieu=request.tenant.domain_url`, et compare le ticket à `request.tenant.domain_url`.

Cinq règles, chacune bloque une attaque précise :

| Règle | Ce qu'elle empêche |
|---|---|
| **Le domaine `lieu=` doit être un `Domain` connu**, d'un tenant autre que `public`. Le guichet construit lui-même l'URL de retour (`https://<lieu>/connexion/retour/`) : il ne reçoit jamais une URL complète | Envoyer le ticket sur un site pirate (redirection ouverte) |
| **Le ticket porte le domaine du lieu**, et le lieu le compare à `request.tenant.domain_url` | Rejouer sur le lieu C un ticket prévu pour B |
| **Le ticket vit 60 secondes** (`signing.loads(..., max_age=60)`) **et ne sert qu'une fois** (`caches["verrous"].add("sso_ticket_utilise:<unique>", 1, 120)` côté lieu : `False` → refusé) | Le rejouer depuis un historique ou un journal |
| **Le `state`** (`secrets.token_urlsafe(32)`) est posé dans la session du lieu avant le départ, puis comparé au retour avec `constant_time_compare`, et retiré de la session | Connecter la victime au compte de l'attaquant (« login CSRF ») |
| **Seulement un compte humain** (`espece == TibilletUser.TYPE_HUM`) : `fabriquer_un_ticket` refuse les autres | Ouvrir une session de terminal (`TermUser`) ou de compte technique sur un lieu |

**Pourquoi l'alias `verrous`.** Le cache par défaut a `ignore_exc` : en panne de memcached,
`cache.add()` renvoie `False` comme si la clé était prise (`settings.py:351-357`). Tous les
tickets seraient refusés comme des rejeux, en silence. L'alias `verrous` lève une exception à
la place : la panne arrive dans Sentry. L'onboarding fait pareil pour son jeton
(`onboard/views.py:638-641`).

**Modèle à suivre :** `_generate_onboard_sso_token` (`onboard/views.py:553`) fait déjà un
jeton de ce genre (120 s, usage unique par `verrous`, humains seulement).

Le ticket ne contient aucune session : seulement « c'est le compte n°X, pour le lieu B ».
C'est le lieu qui ouvre sa propre session.

### 3.4 Ce qui tourne sur le guichet, ce qui tourne « dans le contexte du lieu »

Le guichet tourne sur le schéma `public`. **Le code, ses plafonds et son empreinte vivent sur
le guichet** : le service `connexion_par_code.py` est appelé sans `tenant_context`, donc
`make_key` préfixe ses clés par `public`. Raisons :
- les plafonds (par email, par IP) comptent **tous lieux confondus**. Comptés par lieu, ils
  seraient multipliés par ~500 ;
- un code par lieu ne protégerait rien : une fois connecté sur le guichet, `GET /sso/?lieu=B`
  donne un ticket pour n'importe quel lieu.

**Deux opérations tournent dans `tenant_context(<tenant du lieu>)`** :
- **le `.delay()` du mail** : la tâche Celery hérite du lieu (`TenantAwareCeleryApp`,
  `TiBillet/celery.py:14-17`), lit `Configuration.get_solo()`, et le mail porte le nom du
  lieu ;
- **la finalisation du compte** (§5.4) : le compte créé est rattaché au lieu
  (`client_achat`, `client_source`) et pas à `public`, et la machine à états valide les
  anciennes `F` du lieu (`activator_free_reservation` ne fait rien sur `public`,
  `signals.py:322`).

`login()` sur le guichet et la fabrication du ticket se font hors du `tenant_context`.

**Sessions déjà ouvertes sur le domaine `public`.** L'onboarding connecte la personne sur le
domaine `public` après son propre OTP (`onboard/views.py:380-402`, `713-715`). Cette session
devient de fait une session du guichet : au prochain `GET /sso/`, ticket sans code. C'est
cohérent (l'email a été prouvé), et « Me déconnecter » la ferme aussi (D14).

### 3.5 Ce qui existe déjà et ne change pas

`TiBilletLogin.redirect_session_to_another_tenant` (`views.py:932`) pousse une personne
connectée sur A vers B avec un lien magique (`get_connect_token`, 72 heures). Il sert au
scanner « QR code scan & pay ». **Inchangé** (D3). Un chantier futur pourra le faire passer
par le guichet.

## 4. Les deux OTP du projet

Le projet a **deux** implémentations OTP. **Une seule est branchée.**

| | Onboarding | AuthBillet |
|---|---|---|
| Fichiers | `onboard/services.py` (`generate_otp`, `verify_otp`) | `AuthBillet/otp_service.py` + `otp_session.py` (supprimé en S5, D11) |
| Branché ? | **Oui, en production.** Appelé par `onboard/views.py`. Routes montées dans `TiBillet/urls_public.py:24` et `urls_tenants.py`. | **Non.** Aucun import hors des tests. |
| Où est gardé le code | Champs de `WaitingConfiguration` (schéma `meta`) | Au choix de l'appelant |
| Empreinte | PBKDF2 (`make_password`) | SHA-256 simple |
| Envoi du mail | Tâche Celery `onboard_otp_mailer` | Directement dans la requête (`mail.send()`, `otp_service.py`) |
| Tests | 19 | 33 |

**Pourquoi deux :** le service AuthBillet a été écrit le 2026-05-19 pour le wizard public de
proposition d'événement. Ce wizard est passé à la connexion classique deux jours plus tard
(`CHANGELOG/2026-05-21-wizard-evenement-v2-connexion-classique-lieu-pages.md`). Le service
n'a plus d'utilisateur depuis.

**Dans ce chantier :** on branche les fonctions pures d'`otp_service.py`. L'onboarding ne
bouge pas (sa migration = `OTP/CHANTIER-03`, hors périmètre). `OtpSession` est supprimée
(D11). Ses deux défauts :
- en DEBUG, **n'importe quel code à 6 chiffres est accepté**. Pour une connexion, cela veut
  dire entrer dans n'importe quel compte ;
- son compteur d'essais vit dans la session. Il se remet à zéro si on change de cookie.

## 5. Conception technique

### 5.1 Service `AuthBillet/connexion_par_code.py` (nouveau)

Trois fonctions. Elles ne connaissent ni la requête ni les gabarits. **L'appelant les lance
sur le guichet, sans `tenant_context`** (§3.4) : les clés sont préfixées par `public`.

```python
def cle_cache(email: str, suffixe: str) -> str:
    """Clé de cache d'un email. Sert au service ET au test E2E (§8.2)."""

def envoyer_un_code_de_connexion(email: str, adresse_ip: str | None, langue: str,
                                 lieu: Client) -> str:
    """
    Vérifie les plafonds, fabrique un code, garde son empreinte en cache,
    programme le mail DANS tenant_context(lieu) (nom du lieu dans le mail).
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
par le nom du schéma courant (`KEY_FUNCTION`, `settings.py:324`). `<e>` = les 32 premiers
caractères du SHA-256 de l'email : memcached refuse les clés de plus de 250 caractères et
certains caractères.

| Clé | Valeur | Durée | Rôle |
|---|---|---|---|
| `login_code:<e>:empreinte` | empreinte du code | 600 s | le code en cours |
| `login_code:<e>:essais` | compteur | 600 s | 5 essais au plus |
| `login_code:<e>:dernier_envoi` | `1` | 60 s | délai entre deux envois (`caches["verrous"].add`, atomique) |
| `login_code:<e>:envois_de_l_heure` | compteur | 3600 s | 10 codes par heure et par email |
| `login_code_ip:<ip>:demandes_des_10_min` | compteur | 600 s | `CONNEXION_CODE_PLAFOND_IP_10_MIN` demandes par tranche de 10 minutes et par IP (D9) |

**En panne de memcached** :
- `dernier_envoi` passe par `caches["verrous"]` (§3.3) : la panne lève une exception, elle
  arrive dans Sentry. Avec le cache par défaut, `add()` renverrait `False` et la personne
  lirait « Un code vient de partir » pour toujours ;
- l'empreinte absente → « Ce code a expiré » ;
- les compteurs (cache par défaut) ne comptent plus : les plafonds sont suspendus le temps de
  la panne. Accepté.

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
- **Le lieu est transmis automatiquement** à la tâche (`TenantAwareCeleryApp`), parce que
  le service appelle `.delay()` dans `tenant_context(lieu)`.
- **Langue** : la vue passe `langue=get_language()` (celle de la personne) ; la tâche fait
  `activate(langue)`. Sans cela, gettext envoie le sujet en anglais (`tests/PIEGES.md`,
  P.ONBOARD.5).
- **Envoi** : la tâche appelle `otp_service.envoyer_email_otp(email, code,
  libelle_action=_("Connexion"), nom_organisation=config.organisation)`.
- **Mail pas parti** : `envoyer_email_otp` renvoie `mail.sended` (une ligne à ajouter). La
  tâche écrit une erreur (`logger.error`) si rien n'est parti. Une configuration mail
  invalide lève `ValueError` dans `CeleryMailerClass.send()` : on laisse planter (Sentry).
- **Nouvelles tentatives courtes** : `max_retries=2`, `retry_backoff_max=60`. Ne pas copier
  les réglages de `connexion_celery_mailer` (6 tentatives, jusqu'à 600 s) : ils livreraient
  un code déjà expiré.
- Le code passe en clair par la file Celery, comme pour l'onboarding.

### 5.2 Le service SSO `AuthBillet/sso.py` (nouveau)

Fonctions pures, sans gabarit :

```python
def domaine_du_guichet() -> str:
    """Domaine principal du tenant `public` (Client schema_name="public")."""

def trouver_le_lieu_du_domaine(domaine: str) -> Client | None:
    """Le tenant d'un Domain connu, hors `public`. None sinon."""

def fabriquer_un_ticket(user, domaine_du_lieu: str, avertissement: str = "") -> str:
    """
    signing.dumps({...}, salt="AuthBillet.sso.ticket").
    Refuse (ValueError) un compte non humain : l'appelant vérifie avant.
    """

def lire_un_ticket(ticket: str, domaine_attendu: str) -> dict | None:
    """
    signing.loads(..., max_age=60). Vérifie le domaine et l'usage unique
    (caches["verrous"].add).
    None si le ticket est faux, expiré, prévu pour un autre lieu, ou déjà servi.
    """
```

`domaine_attendu` = `request.tenant.domain_url` (§3.3).

`domaine_du_guichet()` lit la base à chaque appel (une requête par clic sur « Se
connecter ») : pas de cache à invalider.

### 5.3 Vues du guichet (schéma `public`, `TiBillet/urls_public.py`)

Fonctions Django, dans `AuthBillet/views_sso.py` (nouveau). Gabarits dans
`AuthBillet/templates/sso/` : la page étend `seo/base.html` (le squelette des pages du
schéma `public`). **`seo/base.html` ne charge que Bootstrap** (`seo/templates/seo/base.html:109-116`) :
le gabarit du guichet charge htmx lui-même et pose le jeton CSRF (`hx-headers`).
Différence avec le modèle de l'onboarding : `onboard/templates/onboard/base_wizard.html:64`
charge htmx en `defer`, et le CSRF est posé dans chaque étape (`{% csrf_token %}`,
`hx-headers` dans `steps/02_verify.html:166`). Le guichet (`AuthBillet/templates/sso/guichet.html`)
charge htmx en script **bloquant** (`extra_head`, sans `defer`) et pose `hx-headers` une
seule fois, sur `<main>` : les formulaires des deux étapes en héritent.

| Route | Rôle |
|---|---|
| `GET /sso/?lieu=<domaine>&state=<state>` | `lieu` inconnu → page d'erreur « Lien de connexion invalide » (200, sans ticket). Personne déjà connectée sur le guichet, avec un compte humain → ticket et redirection vers le lieu. Sinon → page « Connexion à <nom du lieu> », étape 1 (email) |
| `POST /sso/code/` | Étape 1 → envoie le code (le mail part dans le `tenant_context` du lieu) → partiel de l'étape 2 |
| `POST /sso/code/verifier/` | Étape 2 → vérifie le code, finalise le compte (§5.4), `login()` sur le guichet, `HttpResponseClientRedirect` vers le lieu avec le ticket |

- `lieu` et `state` voyagent dans des **champs cachés** des deux formulaires. Le guichet
  revérifie `lieu` à chaque requête. Rien n'est gardé dans la session du guichet : deux
  onglets ouverts pour deux lieux ne se mélangent pas.
- **Le nom du lieu** (titre de la page, mail) vient de `Configuration.get_solo()` lu dans
  le `tenant_context` du lieu.
- **Réponses htmx** : toujours 200 avec le partiel, le message d'erreur dedans. htmx ne
  remplace pas le contenu d'une réponse 4xx. Jamais de `Http404` ni de `get_object_or_404`.
- `data-testid` : `login-email`, `login-submit`, `login-code`, `login-code-submit`,
  `login-code-resend`, `login-change-email`. Le formulaire de l'étape 1 garde les id
  `loginForm` et `loginEmail` (`tests/e2e/test_login.py`).

**Étape 1 (`POST /sso/code/`)**
1. `LoginEmailValidator` (`validators.py:187`). Invalide → étape 1 avec l'erreur.
2. Sans `tenant_context` :
   `envoyer_un_code_de_connexion(email, get_client_ip(request), get_language(), lieu)`.
3. `"envoye"` ou `"attendre"` → étape 2. `"trop_de_demandes"` → étape 1 avec le message.
4. **Ne crée ni compte ni portefeuille** (corrige A5).

**Étape 2 (`POST /sso/code/verifier/`)**
1. Serializer : `email` (`EmailField`), `code` (`RegexField` `^\d{6}$`), `lieu`, `state`.
2. Sans `tenant_context` : `verifier_le_code_de_connexion(email, code)`. Tout sauf `"ok"` →
   étape 2 avec le message.
3. `"ok"` → dans `tenant_context(lieu)` : finalisation du compte (§5.4). On garde
   l'éventuel texte de `user.message_reservation_annulee` (A8).
4. Hors du `tenant_context` : `login(request, user,
   backend="django.contrib.auth.backends.ModelBackend")` sur le guichet. Le projet n'a qu'un
   backend : l'écrire évite une erreur si on en ajoute un jour.
5. `HttpResponseClientRedirect("https://<lieu>/connexion/retour/?ticket=...&state=...")`,
   avec le message A8 dans le ticket.

**`GET /sso/` d'une personne déjà connectée sur le guichet** : ticket et redirection, sans
rien finaliser. Le compte est forcément activé (sinon le `ModelBackend` n'aurait pas rendu
de session). Compte non humain → page d'erreur « Lien de connexion invalide », pas de ticket.

### 5.4 Finalisation du compte (étape 2 du guichet)

Dans `tenant_context(lieu)`, dans cet ordre :

1. **Compte non humain.** Si un compte existe avec cet email et
   `espece != TibilletUser.TYPE_HUM` (terminal, compte technique) → refus, avec le même
   message que « code faux ». Sans ce contrôle, `get_or_create_user` cherche
   `espece=TYPE_HUM`, ne trouve rien, tente une création, et l'unicité de l'email lève une
   `IntegrityError` → 500 (`AuthBillet/utils.py:113-117`).
2. **Compte.** `user = get_or_create_user(email, send_mail=False)`. S'il renvoie `None`, le
   compte existe avec `email_error=True`. Or le code vient d'arriver : l'adresse marche. On
   remet `email_error=False` (`TibilletUser.objects.filter(email=email).update(email_error=False)`),
   puis on rappelle `get_or_create_user`. `get_or_create_user` rattache aussi le compte au
   lieu (D16).
3. **Si le compte n'est pas encore activé :**
   1. **Anciennes réservations (D12).**
      `Reservation.objects.filter(user_commande=user, status=Reservation.FREERES,
      event__datetime__lt=timezone.now()).update(status=Reservation.CANCELED)`. Un
      `.update()` ne passe pas par la machine à états : c'est voulu, `F` → annulée n'a pas
      de transition.
   2. **Activation.** `is_active=True`, `email_valid=True`, puis **`user.save()`**, pas un
      `.update()` : seul `save()` lance la machine à états. Elle valide les anciennes
      réservations `F` de ce lieu (`activator_free_reservation`).
   3. **Message A8.** `avertissement = getattr(user, "message_reservation_annulee", "")`,
      comme `activate()` (`AuthBillet/views.py:150-154`). Il part dans le ticket.

   Règle **à écrire en commentaire dans le code**, sinon quelqu'un la cassera : **toujours
   l'instance `TibilletUser`** renvoyée par `get_or_create_user`, jamais un proxy
   (`HumanUser`, `SuperHumanUser`). Avec un proxy, `pre_save` part avec un autre nom de
   modèle (`pre_save_signal_status` lit `sender.__name__`, `signals.py:495`) et la machine
   à états ne se déclenche pas.

Le portefeuille Fedow n'est **pas** créé ici : une seule fois, au retour sur le lieu (§5.5).

### 5.5 Vues du lieu (`BaseBillet/views.py`)

| Route | Vue | Rôle |
|---|---|---|
| `GET /connexion/?next=<chemin>` | `connexion` (réécrite) | Déjà connecté → redirection vers `next`. Sinon : `state` et `next` dans la session, redirection vers le guichet. Pas de POST : la route ne sert plus de formulaire |
| `GET /connexion/retour/?ticket=&state=` | `connexion_retour` (nouvelle) | Vérifie et connecte (détail ci-dessous) |
| `GET /login/login_fullpage/?next=<url signée>` | `TiBilletLogin.login_fullpage` | Décode le `next` signé (`signing.loads`, signature fausse → pas de `next`), puis redirige vers `/connexion/?next=<chemin>`. **Son POST disparaît.** Deux appelants : `QrCodeScanPay.process_qrcode` (`views.py:2608`) et l'ancien lien de `booking` |
| `POST /deconnexion/` | `deconnexion` (`views.py:579`) | Déconnexion de partout (§5.6) |

**`next` est toujours un chemin du lieu.** `connexion` le contrôle **avant** de le garder,
avec `url_has_allowed_host_and_scheme(next, allowed_hosts={request.get_host()})`. Refusé →
`/`. Il ne passe jamais par le guichet : seul le `state` y voyage. Pas besoin de le signer.
Le domaine envoyé au guichet est `lieu=request.tenant.domain_url` (§3.3).

**`GET /connexion/retour/`**
1. Retirer **tout de suite** `sso_state` **et** `sso_next` de la session
   (`request.session.pop`). `login()` vide la session quand un autre compte y était connecté
   (`django/contrib/auth/__init__.py:106-116`) : lus plus tard, ils seraient perdus.
2. `state` reçu différent de `sso_state` (`constant_time_compare`) → message d'erreur,
   redirection vers `/`.
3. `lire_un_ticket(ticket, request.tenant.domain_url)` → `None` → message « Le lien de
   connexion a expiré. Reconnectez-vous. », redirection vers `/`.
4. Le compte n'existe pas, n'est pas activé, ou n'est pas humain → même message.
5. **Rattachement (D16)** : `user.client_achat.add(connection.tenant)`. Sans cette ligne,
   une personne venue d'un autre lieu n'apparaît pas dans l'admin de ce lieu
   (`HumanUserManager`, `AuthBillet/models.py:414-422`) ni dans la recherche « Inscrire
   quelqu'un » du bénévolat (`booking/views_benevolat.py:725`).
6. **Portefeuille Fedow** s'il manque (même appel que `views.py:593-595`), dans un
   `try/except` qui journalise l'erreur **sans bloquer** : la connexion passe avant le
   portefeuille. C'est le seul endroit du parcours qui le crée.
7. `login(request, user, backend="django.contrib.auth.backends.ModelBackend")`.
8. Avertissement A8 du ticket → `messages.warning`. Puis message de succès.
9. Redirection vers le `sso_next` lu à l'étape 1, ou `/`.

Pas d'annulation D12 ici : le compte est déjà activé, l'activateur ne tournera pas.

`connexion` et `connexion_retour` sont des fonctions Django, comme `connexion` aujourd'hui.
Le slug `connexion` est déjà réservé (`pages/models.py:48`) : `/connexion/retour/` ne peut pas
entrer en conflit avec une page.

**`booking`** : `cancel_confirm` (`booking/views.py:1121`) redirige déjà vers
`/connexion/?next=<chemin>`. Avec la nouvelle vue `connexion`, ce lien marche tel quel :
aucun changement.

### 5.6 Déconnexion de partout (D14)

Django compare, à chaque requête, une empreinte gardée dans la session à une empreinte
calculée depuis le compte. C'est ce qui déconnecte tous les appareils après un changement de
mot de passe. On y ajoute un champ.

- **Nouveau champ** `TibilletUser.jeton_de_session = CharField(max_length=64, blank=True,
  default="")`. Migration `AuthBillet/0025_...` (schéma `public`, `SHARED_APPS`).
- **Surcharge de `_get_session_auth_hash(self, secret=None)`** (Django 4.2.30, utilisée par
  `get_session_auth_hash` **et** `get_session_auth_fallback_hash`) :
  - `jeton_de_session` vide → `super()._get_session_auth_hash(secret)` : **même empreinte
    qu'aujourd'hui**. Le déploiement ne déconnecte personne ;
  - sinon → `salted_hmac("AuthBillet.TibilletUser.session", self.password +
    self.jeton_de_session, secret=secret, algorithm="sha256").hexdigest()`.
  - Surcharger la méthode privée, pas `get_session_auth_hash` : sinon une
    `SECRET_KEY_FALLBACKS` future rendrait les anciennes sessions valides par l'empreinte de
    secours.
- **Nouvelle méthode** `TibilletUser.deconnecter_de_partout()` :
  `self.jeton_de_session = secrets.token_hex(32)`, puis
  `self.save(update_fields=["jeton_de_session"])`.
- **`deconnexion`** (lieu) : `request.user.deconnecter_de_partout()` si la personne est
  connectée, puis `logout(request)`.
- **Déconnexion depuis l'admin.** Le bouton d'Unfold appelle `AdminSite.logout`, qui ne fait
  que `auth_logout` (`django/contrib/admin/sites.py:383-391`). `StaffAdminSite` surcharge
  `login` mais pas `logout` (`Administration/admin/site.py:36-45`). Surcharger
  `StaffAdminSite.logout` : `request.user.deconnecter_de_partout()` si la personne est
  connectée, puis `super().logout(request, extra_context)`.
- **Effet** : toutes les sessions du compte (tous les lieux, le guichet) deviennent invalides
  à leur prochaine requête. La table des sessions est unique (`django.contrib.sessions` est
  dans les `SHARED_APPS`), mais on n'a pas besoin de la parcourir.
- **Hors effet** : les liens magiques déjà envoyés restent valables (D3). Les terminaux
  (`TermUser`) ont un jeton vide : rien ne change pour eux.

### 5.7 Réservations gratuites validées tout de suite (D15)

Dans `BaseBillet/validators.py`, les trois endroits qui choisissent entre `F` et `FA` posent
désormais **toujours** `FA` (`Reservation.FREERES_USERACTIV`) :

| Endroit | Ligne (2026-10-19) |
|---|---|
| `TicketCreator.__init__`, réservation qui ne contient que des billets gratuits | `validators.py:279-282` |
| `TicketCreator.valider_une_reservation_a_zero_euro` | `validators.py:345-348` |
| `TicketCreator.method_A` (place bénévole) | `validators.py:366` |

- Le passage en `FA` lance `reservation_paid` (`signals.py:255-285`, `444-445`) : billets
  `NOT_SCANNED`, `ticket_celery_mailer` et `webhook_reservation`. Les billets partent par
  mail tout de suite, comme pour un compte activé.
- **API v2 et transaction.** L'API v2 crée la réservation sous `transaction.atomic()`, et ces
  tâches partent **sans `on_commit`** (`api_v2/views.py:705-722`). C'est déjà le cas pour un
  compte activé ; D15 l'étend à toute réservation gratuite par l'API. `ticket_celery_mailer`
  réessaie : boucle de 10 essais à 1 s (`tasks.py:~1745-1751`). `webhook_reservation`
  (`tasks.py:~1814`) ne réessaie pas : s'il part avant le commit, `Reservation.objects.get`
  lève `DoesNotExist` (seulement si le lieu a un webhook actif). Vérifié en S3 : **signalé
  au mainteneur**, aucune garde ajoutée (§12).
- **API v2, représentation.** `api_v2/serializers.py:1711-1728` rend `F` **et** `FA` en
  `https://schema.org/ReservationPending` (jusqu'au `VALID` posé par le mail).
  `api_v2/openapi-schema.yaml:941-944` garde `FREERES (F)` comme filtre : il sert encore aux
  anciennes `F`. Aucune modification ; une ligne dans `api_v2/GUIDELINES.md` : « une
  réservation gratuite créée par l'API n'est plus jamais `F` ».
- **Commentaires de l'admin périmés** : `Administration/admin_tenant.py:5568`, `5602-5612`,
  `5646` (« la réservation attend la validation du mail ») → à corriger.
- **Inchangés** : `CommandeService` (panier, `services_commande.py:554-570`). Il exige déjà
  une personne connectée, donc un compte activé : son `if user.is_active` vaut toujours
  `True`.
- **Inchangé, hors D15** : `booking_engine.py:855` pose `Booking.FREERES` selon
  `member.is_active`. C'est un `Booking` (ressource), pas une `Reservation`. Le bénévolat
  peut y mettre un compte non activé (`booking/benevolat.py:1036`, inscription par un
  gestionnaire). Non traité.
- **Inchangés** : le statut `F`, `activator_free_reservation`, D12 et le message A8.
  Ils traitent les réservations `F` **déjà en base** (anciennes réservations anonymes,
  anciennes réservations API). Elles disparaissent avec le temps. Les retirer = un autre
  chantier, quand il n'en reste plus.
- Commentaire à écrire à chaque endroit : « Toujours `FA` : la réservation vient d'une
  personne connectée (compte forcément activé) ou de l'API v2, à qui l'on fait confiance. »

### 5.8 Gabarits et JavaScript du lieu

**Connexion.**

| Fichier | Changement |
|---|---|
| `BaseBillet/templates/commun/offcanvas/connexion.html` | Le panneau `#loginPanel` ne contient plus de formulaire. Il garde son titre et affiche : un texte court (« Connectez-vous avec votre adresse email. Un code vous sera envoyé. Une seule connexion pour tous les lieux TiBillet. »), et **un lien-bouton** « Se connecter » vers `/connexion/?next=<page courante>` (`data-testid="login-guichet"`). Petit script : à l'ouverture du panneau, si le bouton qui l'a ouvert (`event.relatedTarget`) porte un `data-next`, le copier dans le `next` du lien. Les 15 gabarits qui ouvrent `#loginPanel` ne changent pas |
| `BaseBillet/templates/commun/formulaires/login.html` | **Supprimé** si plus aucun gabarit ne l'inclut (vérifier par `rg`). Le formulaire vit désormais sur le guichet |
| `fonctionnel/connexion/fullpage.html`, `partials/fullpage_inner.html`, `partials/confirmation_inner.html`, `confirmation.html` | **Supprimés** : `login_fullpage` ne rend plus rien. Ces gabarits ont été retouchés le 2026-10-08 (commit 4a744db8) : prévenir son auteur |
| `BaseBillet/templates/htmx/components/panier_scripts.html` (l.126) | Le 403 ouvre `#loginPanel` seulement pour `/panier/`. Étendre le test à `/event/` et `/memberships/` : une session expirée dans un onglet resté ouvert doit ouvrir la connexion, pas rien |

**Réservation et adhésion.**

| Fichier | Changement |
|---|---|
| `BaseBillet/templates/commun/formulaires/reservation.html` | Remplacer **tout** le bloc `{% if user.is_anonymous %}…{% endif %}` du champ email par le champ email en lecture seule, entouré de `{% if user.is_authenticated %}`. La branche « email non confirmé » disparaît avec : c'est du code mort, car un compte non activé est vu comme anonyme. Remplacer le contenu du `{% else %}` anonyme des boutons par **un** bouton « Se connecter pour réserver » : `data-bs-toggle="offcanvas"`, `data-bs-target="#loginPanel"`, `data-next="{{ request.path }}?openbookingPanel=true"`, `data-testid="booking-login"`. Relocaliser les blocs par `rg` (lignes du 2026-09-22 périmées) |
| `BaseBillet/templates/commun/adhesion/form.html` | Pareil : le bloc email devient le champ en lecture seule sous `{% if user.is_authenticated %}`. Le `{% else %}` des boutons devient **un** bouton « Se connecter pour adhérer » (`data-testid="membership-login"`, sans `data-next`) |
| `BaseBillet/static/commun/js/booking-calculator.mjs` | Supprimer le contrôle email / confirmation |
| `BaseBillet/static/commun/js/membership-form.mjs` | Supprimer `emailInput`, `confirmInput`, `errorDiv`, `validateEmails`. Dans `validateAll`, retirer `const okEmails = validateEmails();` et `okEmails && `. Supprimer le branchement des écouteurs sur les deux champs email. **Garder** le contrôle des groupes de cases obligatoires |
| `BaseBillet/templates/fonctionnel/event/reservation_ok.html` | **Supprimé** (« validez votre email ») |

**Attention, `membership-form.mjs`.** Il est chargé dans le même `<script type="module">`
que le changement de thème, de langue et `bs-counter` (`classic/shell.html`, `V2/shell.html`,
`faire_festival/shell.html`). Une erreur de syntaxe dans ce fichier casse ces modules **sur
tout le site**, y compris les compteurs de quantité de la réservation. Vérifier dans Chrome
après modification.

**Règles communes :**
- Les copies de `www/static/` viennent de `collectstatic` : ne jamais les modifier à la main.
- Textes nouveaux : `msgid` en **français**. Ne pas lancer `makemessages` ; le signaler au
  mainteneur en fin de chantier.

### 5.9 Réservation (`EventMVT`) et adhésion (`MembershipMVT`)

**`EventMVT.get_permissions()`** (`views.py:3316`) garde sa branche
`admin_show_event_detail` → `TenantAdminPermission` (**à ne pas perdre** : elle protège les
noms et emails des acheteurs). On ajoute :
`if self.action in ['reservation', 'action_reservation']` → `IsAuthenticated`. Le reste →
`AllowAny`.
- Ne pas raisonner sur la méthode HTTP : `partial_list` (`views.py:3710`) est un **POST
  public** (filtres).
- Retirer le `permission_classes` de l'`@action` d'`action_reservation` : c'est
  `get_permissions()` qui décide (corrige A7).

**`EventMVT.reservation()`** (`views.py:4075`) : `donnees = request.data.copy()`, puis
`donnees["email"] = request.user.email`.
- C'est `IsAuthenticated` qui corrige A1 et A2. L'injection change seulement le résultat
  pour une personne connectée : elle réserve pour elle-même, au lieu de recevoir une erreur
  si l'email posté diffère (par exemple une autre casse).
- `.copy()` garde les listes : `extract_products` lit la copie avec `getlist`. Les champs
  `form__*` sont relus sur `request.data`, l'original, qui contient les mêmes clés. Seul
  `email` diffère entre les deux.
- Supprimer la branche « compte non activé » et le rendu de `reservation_ok.html`
  (`views.py:~4110-4125`). Une réservation gratuite finit toujours sur « Réservation
  validée ! » et la redirection vers `my_account-my-reservations`.
- `stripe_return` : inchangé.

**`MembershipMVT`** (`views.py:4675`) :
- `get_permissions()` (`views.py:6161`) : liste d'actions admin → `TenantAdminPermission`,
  sinon `AllowAny`. Ajouter une branche `create` → `IsAuthenticated`. Aucune autre action
  n'accepte d'adhésion anonyme. (`views.py:4621` est celui de la classe `Badge` : ne pas le
  confondre.)
- `create()` : même injection de `request.user.email`.
- `MembershipValidator` : inchangé (D8).

**Pages intégrées dans un autre site** (`/event/embed/`, `/memberships/embed/`) : dans une
iframe d'un autre site, le cookie de session ne passe pas (`SESSION_COOKIE_SAMESITE='Lax'`,
`settings.py:100`), et la redirection vers le guichet non plus. **À vérifier :** si ces pages
affichent le bouton de connexion, le remplacer par un lien vers la page de l'événement, dans
un nouvel onglet (`target="_blank"`).

### 5.10 Ce qui ne change pas

| Élément | Pourquoi il reste |
|---|---|
| `ReservationValidator`, `MembershipValidator`, `TicketCreator` | API v2, caisse, admin (D8). Seule exception : D15 |
| `get_or_create_user`, `connexion_celery_mailer`, `emails/connexion.html` | Appelés par l'API v2 (nouveaux comptes), la liaison de carte QR, `resend_activation_email`, l'admin et le bénévolat (`booking/benevolat.py:1036`, inscription par un gestionnaire, `send_mail=False`) |
| `/emailconfirmation/` et `AuthBillet.views.activate` | D3. Usages : `redirect_session_to_another_tenant` (`views.py:932`), `go_admin` et `connect_to` (`Administration/admin_tenant.py`), `login_as_user`, commande `get_login_link`, onboarding (`forge_admin_magic_link`), 3 mails (`tasks.py`) |
| `MyAccount.resend_activation_email` (`views.py:1771`) | Les comptes liés par carte QR sont connectés avec `email_valid=False` (`views.py:683`, `738`). Ce bouton reste la voie pour valider leur email sans se déconnecter |
| Statut `F` et `activator_free_reservation` | Pour les `F` déjà en base (§5.7) |
| `ScanQrCode` (dont son lien « TEST MODE ») | D2 |
| OTP de l'onboarding | Hors périmètre (`OTP/CHANTIER-03`) |

### 5.11 Données existantes

**Une migration** : `AuthBillet/0025` (champ `jeton_de_session`, vide par défaut).

**Ordre de déploiement, obligatoire.** La surcharge `_get_session_auth_hash` lit
`jeton_de_session` à **chaque** requête d'une personne connectée. Code redémarré avant la
migration = 500 pour tous les connectés. Donc : `pull` → `migrate_schemas --shared`
(`AuthBillet` est en `SHARED_APPS`, schéma `public` seulement) → redémarrage
`gunicorn daphne celery`.
- Les comptes non activés (anciennes réservations anonymes, API, caisse) le deviennent à
  leur première connexion par code.
- Leurs réservations `F` en attente sur le lieu de cette connexion sont traitées au passage :
  annulées si l'événement est passé (D12), sinon validées si la jauge le permet.
- **Limite acceptée** : une ancienne `F` d'un lieu reste en attente si le compte est activé
  depuis **un autre** lieu (`signals.py:322`). Elles disparaissent avec le temps (D15).
- Les sessions déjà ouvertes restent valides (`SESSION_COOKIE_AGE` = 12 semaines) : le jeton
  de session est vide, l'empreinte ne change pas.

## 6. Parcours cibles

### 6.1 Se connecter sur un lieu

1. La personne clique « Se connecter » (barre de navigation, ou bouton d'un formulaire). Le
   panneau `#loginPanel` s'ouvre, avec un bouton « Se connecter ».
2. Elle arrive sur le guichet : « Connexion à <nom du lieu> ». Elle tape son email et clique
   « Recevoir un code ».
3. Le formulaire se remplace par l'étape 2 : « Un code a été envoyé à `x@y.fr`. Il est valable
   10 minutes. Le code est au début de l'objet du mail. Pas reçu ? Regardez vos indésirables,
   ou demandez un nouveau code dans une minute. » Un champ « Code », un bouton « Me
   connecter », un bouton « Recevoir un nouveau code » et un lien « Changer d'adresse ».
4. Code juste : la personne revient sur la page du lieu d'où elle est partie, connectée.

| Cas | Ce que voit la personne |
|---|---|
| Déjà connectée sur le guichet (2ᵉ lieu) | Rien à taper : retour immédiat, connectée |
| Email mal écrit | Étape 1, message sous le champ |
| Nouveau code demandé moins de 60 s après le précédent | Étape 2 : « Un code vient de partir. Patientez une minute avant d'en demander un autre. » |
| Plafond par email ou par IP atteint | Étape 1 : « Trop de demandes. Réessayez un peu plus tard. » |
| Code faux | Étape 2 : « Code incorrect. Vérifiez le code reçu par mail. » |
| 5 codes faux | Étape 2 : « Trop d'essais. Demandez un nouveau code. » |
| Code expiré (plus de 10 minutes) ou déjà utilisé | Étape 2 : « Ce code a expiré. Demandez un nouveau code. » |
| Une ancienne réservation gratuite ne peut plus être validée (événement complet) | Connexion réussie, avec en plus le message d'avertissement de `activator_free_reservation` |
| Ticket expiré (page du guichet laissée ouverte, puis retour) | Sur le lieu : « Le lien de connexion a expiré. Reconnectez-vous. » |
| Lien du guichet avec un `lieu` inconnu | Guichet : « Lien de connexion invalide. » |
| Déjà connectée sur le lieu, et ouvre `/connexion/` | Redirection vers `next`, rien d'autre |
| Une autre personne était connectée sur ce navigateur | `login()` vide la session : la nouvelle personne est connectée |

### 6.2 Se déconnecter

« Me déconnecter » sur n'importe quel lieu : la personne est déconnectée de ce lieu, du
guichet et de tous les autres lieux. Sur un autre onglet, elle apparaît déconnectée au
prochain clic.

### 6.3 Réserver un billet

- **Anonyme** : il voit les tarifs. Un seul bouton : « Se connecter pour réserver ». Il ouvre
  `#loginPanel`. Après la connexion, la page revient **avec le panneau de réservation
  ouvert** (`?openbookingPanel=true`, déjà géré par les 3 skins : classic, V2,
  faire_festival).
- **Connecté** : rien ne change (« Payer maintenant », « Ajouter au panier »).

**Pourquoi rouvrir le panneau :** sans réouverture, la personne doit, sur son téléphone,
retrouver le bouton « Réserver » après la connexion.

### 6.4 Adhérer

Pareil : « Se connecter pour adhérer » pour un anonyme. Rien ne change pour un connecté.
Pas de paramètre d'ouverture automatique pour l'adhésion : après la connexion, la personne
rouvre le panneau (accepté).

## 7. Limites et sécurité

| Règle | Valeur | D'où |
|---|---|---|
| Durée de vie d'un code | 10 minutes | `OTP_TTL_SECONDS` |
| Essais par code | 5 | `OTP_MAX_ATTEMPTS` |
| Délai entre deux envois au même email | 60 s | `OTP_RESEND_COOLDOWN_SECONDS` |
| Codes par heure et par email | 10 | nouveau. 10 plutôt que 5 : quelqu'un dont le mail arrive dans les indésirables reclique plusieurs fois |
| Demandes de code par IP | 500 par tranche de 10 minutes, réglable | D9 |
| Usage unique du code | clés effacées après un succès | §5.1 |
| Portée d'un code et des plafonds | le guichet, tous lieux confondus | clés préfixées par `public` (§3.4) |
| Durée de vie d'un ticket | 60 secondes, une seule fois, un seul lieu | §3.3 |
| Session du guichet | même durée que celle des lieux (12 semaines) | `SESSION_COOKIE_AGE` |
| DEBUG | code dans le journal serveur, aucun code universel | D7 |

- **Deviner un code** : 10 codes par heure × 5 essais = 50 essais par heure et par compte,
  soit environ 1 chance sur 20 000 par heure. Les plafonds sont sur le guichet : viser
  plusieurs lieux ne donne pas plus d'essais.
- **Comptes non humains** (terminaux, comptes techniques) : jamais de ticket, jamais de
  finalisation (§5.3, §5.4).
- **Savoir si un compte existe** : impossible par ce formulaire. La réponse de l'étape 1 est
  la même dans tous les cas ; le compte n'est créé qu'après le bon code.
- **Bloquer quelqu'un d'autre** : possible. Qui connaît un email peut épuiser ses codes de
  l'heure, ou les essais du code en cours. L'effet dure au plus une heure, et aucune donnée
  n'est exposée. **Risque accepté** (Keycloak a le même).
- **Pas de plafond par IP sur la vérification.** Risque accepté : la probabilité par compte
  reste celle de la première ligne.
- **Session du guichet volée** = accès à tous les lieux. Même protection que les sessions des
  lieux : cookie `Secure`, `HttpOnly`, host-only. « Me déconnecter » la ferme (D14).
- **Protection « bounce tracking » des navigateurs.** Chrome et Safari peuvent effacer les
  cookies d'un site qui ne fait que rediriger, sans clic de la personne, pendant longtemps
  (Chrome : 45 jours). Effet : retaper un code sur le guichet, pas une panne.

## 8. Tests

**Règles :**
- **Vérification par mutation** : chaque nouveau test doit être vu **échouer** sur une
  modification volontaire du code avant d'être livré.
- Lancer les tests : skill `tibillet-test`. Fichiers ciblés uniquement
  (`docker exec lespass_django bash -c "ulimit -v 8000000; timeout 600 poetry run pytest
  /DjangoFiles/tests/pytest/<fichier>.py -v"`). **La suite complète se lance sur accord du
  mainteneur** : d'autres agents travaillent sur la même base.
- Citer les tests par **nom de fonction**, pas par numéro de ligne : les lignes bougent.

### 8.1 Nouveaux tests pytest

- **Service code** (`connexion_par_code.py`) :
  - le code est gardé en cache et le mail programmé ;
  - le délai de 60 s ;
  - le plafond par email ;
  - le plafond par IP, avec une petite valeur posée par `override_settings`
    (`CONNEXION_CODE_PLAFOND_IP_10_MIN`) ; le `logger.warning` quand il est atteint ;
    une IP `None` n'est pas comptée ;
  - la vérification : `ok`, `faux`, `expire`, `bloque` ;
  - l'usage unique ;
  - un nouveau code remplace l'ancien ;
  - les clés sont posées sur `public`, et le mail est programmé dans le contexte du lieu
    (la tâche patchée voit `connection.schema_name` du lieu).
- **Service SSO** (`sso.py`) :
  - un ticket lu par le bon lieu → le compte ;
  - un ticket lu une 2ᵉ fois → `None` ;
  - un ticket pour B lu par C → `None` ;
  - un ticket de plus de 60 s → `None` (patcher le temps de `signing`) ;
  - un ticket modifié à la main → `None` ;
  - `fabriquer_un_ticket` refuse un compte non humain ;
  - `trouver_le_lieu_du_domaine` : domaine inconnu → `None`, domaine de `public` → `None`.
- **Guichet** (client de test avec `HTTP_HOST` = domaine de `public`) :
  - `GET /sso/` avec un `lieu` inconnu → page d'erreur, aucune redirection ;
  - `POST /sso/code/` ne crée **ni compte ni portefeuille** (A5) ;
  - le bon code crée un compte activé, connecté sur le guichet, rattaché au lieu, et renvoie
    une redirection vers `https://<lieu>/connexion/retour/` ;
  - le bon code valide une ancienne réservation `F` du lieu ;
  - le bon code annule une ancienne réservation `F` d'un événement passé (D12) ;
  - le cas A8 (ancienne réservation, événement devenu complet) connecte quand même, avec le
    message dans le ticket ;
  - un compte avec `email_error=True` se connecte ;
  - l'email d'un compte non humain (`TermUser`) → refusé, pas de 500 ;
  - déjà connecté sur le guichet : `GET /sso/` redirige tout de suite avec un ticket.
- **Lieu** :
  - `GET /connexion/?next=/event/x/` → redirection vers le guichet, `state` en session ;
  - `next` vers un autre domaine → gardé comme `/` ;
  - `GET /connexion/retour/` avec un bon ticket et le bon `state` → connecté, lieu rattaché,
    redirigé vers `next` ;
  - mauvais `state` → pas connecté ;
  - ticket rejoué → pas connecté ;
  - un autre compte était connecté sur le navigateur → la nouvelle personne est connectée et
    arrive quand même sur `next` ;
  - Fedow en panne : la connexion réussit quand même ;
  - `GET /login/login_fullpage/?next=<signé>` → redirection vers `/connexion/?next=<chemin>`.
- **Déconnexion de partout** :
  - un compte au jeton vide garde la même empreinte de session qu'avant le chantier
    (comparer à `AbstractBaseUser._get_session_auth_hash`) ;
  - après `/deconnexion/` sur le lieu A, une 2ᵉ session du même compte (autre client de
    test) est anonyme ;
  - même chose après la déconnexion de l'admin (`admin:logout`).
- **Réservations gratuites (D15)** :
  - par l'API v2, une réservation gratuite pour un email au compte non activé est `FA`, et le
    mail des billets est programmé.
- **Réservation et adhésion** :
  - anonyme → 403, pour `reservation`, `action_reservation` (A7) et `memberships/create` ;
  - `partial_list` (POST) reste public ;
  - `admin_show_event_detail` reste réservé aux admins du lieu ;
  - un connecté qui poste l'email d'un autre réserve **pour lui-même** ;
  - un tarif réservé aux adhérents est refusé à un connecté non adhérent (A2).
- **Pièges :**
  - **Isoler le cache sans le vider.** Un email unique par test
    (`f"code-{uuid4().hex[:8]}@test.local"`) et une IP unique par test (`REMOTE_ADDR`). En
    fin de test, `cache.delete_many([...])` des clés de cet email et de cette IP, dans le
    contexte de `public` (là où vivent les clés, §3.4). **Jamais `cache.clear()`** : sur memcached c'est un `flush_all`, tous
    lieux confondus, et le serveur de dev partage ce memcached (`tests/PIEGES.md`, section
    « Ne PAS utiliser `cache.clear()` »).
  - **Patcher les tâches Celery.** Sous `django_db`, `on_commit` ne part pas. Mais un
    `.delay()` direct part vers le **vrai** broker : le projet n'a pas de
    `task_always_eager`. Patcher la tâche mail du code **et**
    `BaseBillet.signals.ticket_celery_mailer` et `webhook_reservation`, appelées par
    `reservation_paid` quand une réservation passe en `FA`.
  - **`tenant_context`, pas `schema_context`** pour le lieu : `schema_context` pose un
    `FakeTenant`, et `get_or_create_user` lit `connection.tenant`.
  - Citer les pièges de `PIEGES.md` par **titre** : certains numéros existent deux fois.

### 8.2 Nouveaux tests E2E

Un test E2E ne peut pas lire le mail. Il procède ainsi :
1. depuis un lieu, il clique « Se connecter » et arrive sur le guichet ;
2. il demande un code ;
3. via `django_shell(..., schema="public")`, il remplace l'empreinte en cache par celle
   d'un code connu. Les clés du code vivent sur **`public`** (le guichet, §3.4), pas sur le
   lieu. La clé est construite en important `cle_cache` du service (jamais recopiée à la
   main). Aucune contrainte de guillemets : `django_shell` exécute le code par `exec()`
   dans le processus pytest (`tests/e2e/conftest.py`), sans passer par un shell ;
4. il tape ce code et vérifie qu'il est revenu sur le lieu, connecté ;
5. **SSO** : il ouvre un 2ᵉ lieu (`festival`), clique « Se connecter », et vérifie qu'il est
   connecté sans taper de code ;
6. **Déconnexion de partout** : il se déconnecte sur le 2ᵉ lieu et vérifie qu'il est
   déconnecté sur le 1er ;
7. variante réservation : depuis le bouton « Se connecter pour réserver », il vérifie que le
   panneau de réservation est rouvert après la connexion.

Le reste de la suite continue de se connecter par `login_as` (`__test_only__/force_login/`).

### 8.3 Tests existants à reprendre

| Fichier | Tests | Action |
|---|---|---|
| `tests/pytest/test_parite_avec_sans_panier.py` | `test_p2bis_billet_payant_a_zero_euro_pour_un_visiteur_anonyme`, `test_deux_reservations_gratuites_d_un_visiteur_non_active_attendent_l_activation` | Supprimer |
| idem | `test_une_reservation_gratuite_confirmee_apres_20_minutes_reste_valide` | Réécrire : créer une réservation `F` directement en base (une ancienne `F`), puis activer le compte |
| idem | les **trois** asserts `== Reservation.FREERES` (vers l.1493, 2076, 2267) | Relire : après D15, une réservation gratuite n'est plus jamais `F` à la création |
| `tests/pytest/test_en_ligne_ecrit_la_vente.py` | le test de réservation anonyme qui attend `FREERES` (vers l.722-735) | Client connecté, statut `FA` |
| `tests/pytest/test_reservation_admin_envoi_mail.py`, `test_recap_quotidien.py` | créent des `F` directement en base | Inchangés (anciennes `F`) |
| `tests/pytest/test_parite_avec_sans_panier.py` | docstring du module | Retirer le « périmètre anonyme ». Les helpers `reserver_des_billets` et `adherer` reçoivent déjà un client connecté |
| `tests/pytest/test_stripe_membership_simple.py` | `test_anonymous_membership_paid`, `test_anonymous_membership_dynamic_form`, `test_membership_free_price`, `test_ssa_membership_tokens` | Client connecté |
| `tests/pytest/test_stripe_membership_complex.py` | les tests qui passent par `_submit_membership` | Client connecté |
| tous les tests | `rg -n "FREERES\b" tests/` et `rg -n "== ?['\"]F['\"]" tests/` | Tout test qui attend `F` à la création d'une réservation passe à `FA` (D15) |
| `tests/e2e/test_reservation_validations.py` | `test_booking_form_validation_errors` | `login_as` ; supprimer l'étape de confirmation d'email |
| `tests/e2e/test_stripe_smoke.py` | `test_smoke_membership_stripe_checkout`, `test_smoke_booking_stripe_checkout` | `login_as` |
| `tests/e2e/test_numeric_overflow_validation.py` | `test_membership_rejects_oversized_custom_amount`, `test_booking_rejects_oversized_custom_amount` | `login_as` |
| `tests/e2e/test_reservation_limits.py` | `test_stock_max_and_membership_messages`, étapes de l'affichage anonyme | Revoir l'affichage anonyme |
| `tests/e2e/test_membership_validations.py` | `test_membership_form_validation_errors` | `login_as` ; supprimer le contrôle de confirmation |
| `tests/e2e/test_membership_free_price_multi.py` | les 4 scénarios (helper `_remplir_formulaire_base`) | `login_as` |
| `tests/e2e/test_membership_dynamic_form_full_cycle.py` | `test_step2_public_subscribes_with_dynamic_form` et les étapes suivantes | `login_as` |
| `tests/e2e/test_membership_manual_validation.py` | `test_request_and_approve_membership` | `login_as` |
| `tests/e2e/test_login.py` | `test_should_validate_email_format` | Le formulaire est sur le guichet : passer par le panneau puis le guichet. Les id `loginForm` / `loginEmail` restent |
| `tests/e2e/test_panier_flow.py` | `test_e2_un_anonyme_qui_veut_ajouter_au_panier_voit_le_panneau_de_connexion` | Le bouton devient `booking-login` |
| `tests/e2e/test_adhesion_recompense_puis_qrcode.py` | `test_adhesion_en_ligne_payee_par_stripe_credite_mon_espace_puis_se_depense_par_qrcode` | Compte créé et activé par `django_shell`, puis `login_as` ; l'email du formulaire est lu (lecture seule), plus tapé |
| `tests/pytest/test_otp_session.py` | tous | Supprimés avec `OtpSession` (D11) |

**Inchangés (à vérifier quand même) :**
- `test_reservation_subevent_tickets.py` : il appelle `ReservationValidator` directement ;
- `test_qrcodescanpay_flux_complet.py` : il vérifie seulement la redirection vers
  `/login/login_fullpage` avec `next=` ;
- `test_management_commands.py::test_get_login_link` : le lien magique reste (D3) ;
- les tests de l'API v2 : ils passent par les validateurs. Seul D15 peut changer un statut
  attendu.

## 9. Découpage en sessions

| Session | Contenu | Fin de session |
|---|---|---|
| S1 | Service `connexion_par_code.py`, réglage `CONNEXION_CODE_PLAFOND_IP_10_MIN` (`settings.py` + `env_example`), tâche mail, empreinte (D10), tests du service | Tests du service verts |
| S2 | Service `sso.py`, vues et gabarits du guichet (`urls_public.py`), finalisation du compte (§5.4), vues `connexion` et `connexion_retour` du lieu, `login_fullpage` (redirection), tests pytest | Connexion par le guichet utilisable en tapant `/connexion/` ; SSO entre deux lieux ; tests ciblés verts |
| S3 | Déconnexion de partout (§5.6, migration `AuthBillet/0025`, admin), validation immédiate des réservations gratuites (§5.7), tests, reprise des tests qui attendent `F` | Tests ciblés verts |
| S4 | Panneau `#loginPanel` et suppression des anciens gabarits de connexion (§5.8). Réservation et adhésion réservées aux connectés : permissions, injection de l'email, gabarits, JS, `panier_scripts.html`, iframes, **et reprise des tests qu'elles cassent** (§8.3) ; E2E du §8.2 | Tests ciblés verts ; suite complète sur accord du mainteneur |
| S5 | Suppression d'`OtpSession` (D11). `CHANGELOG/`. Mise à jour de `OTP/INDEX.md`. Ajouts à `tests/PIEGES.md` (liste ci-dessous). Chaînes i18n signalées | Docs à jour |

À ajouter ou corriger dans `tests/PIEGES.md` :
- un compte non activé est vu comme anonyme ;
- un `get_permissions()` écrit en dur écrase le `permission_classes` des `@action` (A7) ;
- l'activation d'un compte sur le guichet (schéma `public`) ne valide pas les anciennes `F`
  du lieu : la finalisation tourne dans `tenant_context(lieu)` (§3.4) ;
- un `cache.add()` qui sert de verrou ou d'usage unique passe par `caches["verrous"]`
  (le cache par défaut renvoie `False` en panne) — vérifier qu'une entrée ne le dit pas déjà ;
- `request.get_host()` garde le port, `request.tenant.domain_url` non : c'est lui qui
  correspond à un `Domain` ;
- corriger « le projet a plusieurs backends » (entrée 9.98, « force_login(term_user) ne pose
  PAS set_expiry ») : il n'en a qu'un. Même correction dans le commentaire de
  `onboard/views.py` qui le dit ;
- corriger l'entrée 9.99, qui recommande encore `cache.clear()` avant chaque appel du bridge,
  en contradiction avec la section « Ne PAS utiliser `cache.clear()` ».

`OTP/INDEX.md` est périmé : il dit `step0_verify` encore en place, et propose `OtpSession`.

## 10. C'est fini quand

- Tests ciblés verts ; `make test` et `make e2e` verts (lancés sur accord du mainteneur).
- Un anonyme ne voit que « Se connecter pour réserver » ou « Se connecter pour adhérer ».
- `POST /sso/code/` n'écrit rien en base.
- Une connexion par code réussit sur le lieu de démo, avec le code lu dans le journal (DEBUG).
- Connecté sur `lespass`, on se connecte sur `festival` d'un seul clic, sans code.
- « Me déconnecter » sur `festival` déconnecte aussi de `lespass`.
- Après une connexion depuis le formulaire de réservation, le panneau de réservation est
  rouvert.
- `CHANGELOG/` est écrit, `OTP/INDEX.md` et `tests/PIEGES.md` sont à jour.
- Les nouvelles chaînes à traduire sont signalées au mainteneur.

## 11. Hors périmètre

- Liaison d'une carte QR (D2).
- Remplacer le lien magique (D3), y compris dans `redirect_session_to_another_tenant`.
- Migrer l'OTP de l'onboarding (`OTP/CHANTIER-03`).
- Proposition d'événement anonyme (`EventWizard`, `proposition_anonyme_autorisee`).
- `Booking.FREERES` posé par `booking_engine.py:855` pour un compte non activé (§5.7).
- Retirer le statut `F` et `activator_free_reservation` (quand il n'y aura plus de `F` en base).
- La route cassée `/api/user/activate/<uid>/<token>` (`AuthBillet/urls.py:31`).
- Un plafond réseau (`limit_req` nginx).
- Rouvrir automatiquement le panneau d'adhésion après la connexion.
- Une page « mes sessions » (voir et fermer chaque appareil).

## 12. Décisions en attente

Relevées pendant la réalisation. Rien n'est changé dans le code : le mainteneur tranche.

| # | Sujet | Constat | Options |
|---|---|---|---|
| E1 | `webhook_reservation` sans `on_commit` | `reservation_paid` (`BaseBillet/signals.py`) appelle `webhook_reservation.delay()` directement. Sous `transaction.atomic()` (API v2), la tâche peut partir avant le commit. Elle ne réessaie pas : `Reservation.objects.get` lève `DoesNotExist`, le webhook du lieu n'est pas appelé. D15 rend ce cas plus fréquent (toute réservation gratuite par l'API passe en `FA`) | Passer l'appel en `transaction.on_commit(...)`, comme `send_refund_to_laboutik` ; ou laisser tel quel |
| E2 | `/deconnexion/` en GET | La vue `deconnexion` répond au GET. Avec D14, elle ferme **toutes** les sessions du compte. Une page tierce peut la déclencher (`<img src="https://<lieu>/deconnexion/">`) : la personne est déconnectée de partout, sans rien avoir cliqué. Pas de fuite de données, mais une gêne | **Tranché le 2026-10-20 : POST.** `deconnexion` porte `@require_POST`, `StaffAdminSite.logout` refuse le GET (Django 4.2 l'accepte encore sur `/admin/logout/`). Les liens « Me déconnecter » des 3 skins sont des petits formulaires POST avec `{% csrf_token %}` |
