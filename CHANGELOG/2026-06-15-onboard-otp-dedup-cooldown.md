# Onboarding — fin de la cascade de mails OTP + durcissement endpoint public

**Date :** 2026-06-15
**Migration :** Non

## Origine du problème (important)

Les mails « *XXXXXX – your TiBillet verification code* » viennent du wizard de
**création d'espace** (`onboard`, step `identity`), **PAS** de « Proposer un
évènement » (agenda participatif `proposition_anonyme_autorisee`). Ce sont deux
features distinctes :

- `onboard.tasks.onboard_otp_mailer` n'a qu'un seul appelant : `onboard/views.py`.
- Le wizard de proposition d'évènement (`BaseBillet`) crée l'utilisateur avec
  `send_mail=False` et n'envoie aucun OTP.

L'endpoint `/onboard/identity/` est **public** (`AllowAny`, sur ROOT). Le scénario
réel des ~12 mails en ~3 s pour `dannychan_1023@hotmail.com` n'est pas un humain
qui double-clique, mais un **email-bombing** (un attaquant inonde la boîte d'une
victime via le formulaire d'inscription public) ou un **bot**.

## Ce qui a été fait

| # | Protection | Fichier |
|---|---|---|
| 1 | **Dédup par email** (cause racine) : réutilise un brouillon non confirmé existant au lieu d'en créer un nouveau | `onboard/views.py` |
| 2 | **Cooldown 60 s** : pas de ré-envoi OTP si un mail est parti depuis < 60 s | `onboard/views.py` |
| 3 | **Captcha** arithmétique (`x + y == answer`) sur la step identity | `onboard/serializers.py`, `01_identity.html` |
| 4 | **Throttle** abaissé 20 → 10/min, calé sur la vraie IP (`get_client_ip`) | `onboard/views.py` |
| 5 | **Anti-double-submit** : bouton « Continuer » désactivé au submit | `01_identity.html` |

## Tests à réaliser

URL du wizard (ROOT) : `https://tibillet.localhost/onboard/` (pas un sous-domaine
tenant — le wizard redirige tout accès tenant vers ROOT).

### Test 1 : captcha visible et bloquant
1. Aller sur `/onboard/identity/`.
2. **Attendu :** une question « Anti-spam — Combien font X + Y ? » avec un champ réponse.
3. Remplir le formulaire avec une **mauvaise** réponse → soumettre.
4. **Attendu :** la page se ré-affiche (422), message « Mauvaise réponse à la
   question anti-spam. », **aucun mail** reçu. Un **nouveau** calcul est affiché.
5. Refaire avec la **bonne** réponse → redirection vers `/onboard/verify/`, **1** mail OTP.

### Test 2 : double soumission rapide (le bug d'origine)
1. Remplir identity (bon captcha) et cliquer « Continuer » **plusieurs fois très vite**.
2. **Attendu :** le bouton se désactive ; **un seul** mail OTP ; en base, **un seul**
   `WaitingConfiguration` pour cet email.

### Test 3 : reprise (même email, après cooldown)
1. Faire le Test 2, attendre **> 60 s**, revenir sur identity, re-saisir le **même email**.
2. **Attendu :** pas de nouveau brouillon (réutilisé), **1 nouvel** OTP (cooldown écoulé).

### Test 4 : throttle IP
1. Soumettre identity **> 10 fois en moins d'une minute** depuis la même machine.
2. **Attendu :** au-delà de 10, réponse silencieuse 429 (plus de création/mail).
   ⚠️ Un vrai créateur ne POST qu'une fois → aucune gêne.

### Tests automatisés
```bash
docker exec lespass_django poetry run pytest \
  onboard/tests/test_step_identity.py onboard/tests/test_step_verify.py -q
```
Inclut : `..._same_email_twice_reuses_draft_and_skips_second_otp`,
`..._wrong_captcha_returns_422`, `..._rate_limit_429_over_quota_per_minute` (quota 10).

### Vérification en base (schema `meta`)
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c \
"from django_tenants.utils import schema_context; from MetaBillet.models import WaitingConfiguration
with schema_context('meta'):
    print(WaitingConfiguration.objects.filter(email__iexact='TON_EMAIL').count())"
```
Doit afficher `1` après plusieurs soumissions du même email.

## i18n
Nouveaux textes FR sur la step identity → régénérer les traductions (côté mainteneur) :
```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
# remplir locale/en/LC_MESSAGES/django.po (msgstr EN), puis :
docker exec lespass_django poetry run django-admin compilemessages
```

## Compatibilité
- **Aucune migration** (pas de changement de modèle).
- Branche `skip_otp` (user authentifié + email valide) **inchangée** : brouillon neuf,
  pas d'OTP, redirection directe vers Venue. (Le captcha reste demandé à tous au POST.)
- `resend_otp` (bouton « Renvoyer ») inchangé : cooldown 60 s + rate-limit 3/h.
- **Limite connue :** dédup non atomique sous concurrence stricte ; captcha + throttle 10/min
  + anti-double-submit sont les filets. Abus multi-IP/multi-email limité mais non éliminé.
