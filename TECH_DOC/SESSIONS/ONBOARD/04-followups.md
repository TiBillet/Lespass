# Onboard — Follow-ups & must-have à explorer

Liste consolidée de ce qui reste à faire pour un onboard "production-grade" et de tout ce que l'audit critique a soulevé.

Classé par priorité d'attaque.

---

## 🔴 Bloquants prod (à régler avant ouverture publique)

### F1. Fedow non configuré → boucle retry
**Status** : noté en code, pas fixé.
**Source** : audit code critique (S2).

`wc.create_tenant()` raise si `FedowConfig.can_fedow()` est False (cf. `BaseBillet/validators.py:1026`). Sur un nouveau tenant fraîchement provisionné via le pool, `FedowConfig` est solo et n'a pas encore été configuré → exception → `autoretry_for=(Exception,)` × 3 → `wc.error_message` set → UI "Réessayer" en boucle infinie.

**Pistes** :
- Option A : capturer cette exception spécifique dans `create_tenant_from_draft`, écrire un `error_message` clair "Configuration Fedow manquante — contactez un admin" et **ne pas** retry (pas un cas qui se résout tout seul).
- Option B : pre-configurer `FedowConfig` lors de la création des tenants du pool (`create_empty_tenant` management command).
- Option C : retarder l'appel `can_fedow()` au premier usage réel (paresseux).

**Décision recommandée** : Option B (pool slots déjà configurés Fedow). Plus simple, supprime la dépendance.

---

### F2. Tests Playwright E2E manquants
**Status** : Task 23 du plan, reportée.

3 scénarios critiques à couvrir :
1. **Golden path** : identity → verify (DEBUG bypass) → place → descriptions → events → launch → status done.
2. **Invitation** : `/onboard/?invite=<code>` → WC attaché à `wc.invitation`.
3. **Resume magic link** : envoyer un email avec lien signé, retrouver le brouillon.
4. **Double-click finalize** : tester que la race condition B1 est bien fixée (le claim Redis empêche le double tenant).
5. **OTP paste** : copier "123456" dans la 1e case → vérifier que les 6 cases sont remplies.
6. **Carte Leaflet** : tile loading + marker drag + click.

**Notes** : ne pas relancer `runserver_plus` (le mainteneur le tient dans byobu). Tests doivent tourner contre le port 8002 / Traefik.

---

### F3. CHANGELOG.md + A TESTER + i18n
**Status** : Task 24 du plan, reportée.

À faire :
1. **CHANGELOG.md** : entrée formatée (FR/EN, fichiers modifiés, migrations).
2. **`A TESTER et DOCUMENTER/onboard-wizard.md`** : checklist de tests manuels pour le mainteneur (golden path, dark mode, mobile, reduce-motion, screen reader, invitation flow).
3. **`makemessages -l fr -l en`** + remplir les `msgstr` manquants + `compilemessages`.
   - Toutes les strings `_()` Python + `{% translate %}` / `{% blocktranslate %}` templates.
   - Vérifier qu'aucune fuzzy traduction n'est insérée par erreur.

---

## 🟠 SHOULD-fix (qualité prod)

### S1. Gestion d'erreur si Celery worker absent
Quand le mainteneur lance le wizard en dev sans worker Celery :
- `onboard_otp_mailer.delay()` enqueue dans Redis mais le mail n'arrive jamais.
- `create_tenant_from_draft.delay()` idem → tenant jamais créé, polling 5min → timeout.

**Pistes** :
- **Heartbeat Celery** : exposer un endpoint `/healthz/celery` qui retourne 503 si pas de worker actif depuis N minutes (via Redis ping).
- **Banner UI** dev : `if settings.DEBUG and not _celery_alive()` → bandeau "Worker Celery inactif, certaines actions ne fonctionneront pas".
- Documenter dans `A TESTER` la commande pour lancer le worker en dev (`celery -A TiBillet worker -l info`).

### S2. Logs PII (Personally Identifiable Info)
**Audit** : `geocode()` warning loggue l'adresse complète (tronquée à 40 chars). Mailer ne loggue que l'email + UUID (OK).

**Action** : double-checker que rien d'autre ne loggue email/nom complet/IP.
```bash
grep -rn "logger.*email\|logger.*phone\|logger.*ip" /home/jonas/TiBillet/dev/Lespass/onboard/
```

### S3. Onglets multiples concurrents
Que se passe-t-il si l'utilisateur ouvre 2 onglets sur `/onboard/identity/`, remplit 2 emails différents, soumet les deux ?
- 2 WC créés en DB.
- Session du dernier onglet écrase la session du premier.
- Le premier brouillon orphelin sera purgé par `purge_stale_onboard_drafts` après 30j.

**Acceptable** ? Probablement OK. À documenter dans `A TESTER`.

### S4. Brouillon trouvé / reprise depuis identity
Spec §3.2 ligne 107 : "si l'utilisateur saisit un email qui matche un WC existant non finalisé, proposer 'Reprendre votre brouillon en cours ?'".

**Status** : non implémenté. Actuellement, soumettre identity avec un email déjà utilisé → crée un nouveau WC (orphelinise l'ancien).

**Action** : dans `identity` POST, avant `objects.create()`, faire `WaitingConfiguration.objects.filter(email=data["email"], tenant__isnull=True).first()`. Si existe → page intercalaire "Brouillon trouvé, le reprendre ? [Oui / Recommencer]".

### S5. Préview UI (visualiser le tenant avant lancement)
Step 5 → 6 : l'utilisateur clique "Lancer mon espace" sans avoir vu le rendu final de sa page publique.

**Idée** : ajouter une mini-prévisualisation sur Step 6 (avant le lancement) — vignette de la page d'accueil future avec logo + short_description + premier event. Ou simplement un bouton "Prévisualiser" qui ouvre une modale.

### S6. Captcha sur identity (anonymous abuse)
Spec §1 ligne 102 : "captcha pour user anonyme". Pas encore implémenté.

**Risque** : bot qui spamme `/onboard/identity/` → crée des centaines de WC + envoie des centaines d'emails OTP (via Mod 1 maintenant moins critique car OTP envoyé seulement sur clic, mais reste un vecteur).

**Action** : intégrer `django-simple-captcha` (déjà dans `pyproject.toml`) ou hCaptcha sur le form identity quand `request.user.is_anonymous`.

### S7. Rate-limit identity POST
Actuellement, aucun rate-limit sur `/onboard/identity/` POST. Un attaquant peut créer N WC par seconde.

**Action** : ajouter un `AnonRateThrottle` (5/min/IP via `get_client_ip`) sur l'action `identity` POST.

### S8. Token CSRF expiré sur sessions longues
Si l'utilisateur laisse le wizard ouvert 24h+, le token CSRF expire. Le submit final échoue silencieusement (ou 403).

**Action** : tester en E2E. Soit augmenter `CSRF_COOKIE_AGE`, soit prévenir l'utilisateur avant expiration.

---

## 🟡 Must-have d'une app d'onboard moderne (idées à creuser)

### M1. Email magique sans mot de passe (passwordless first)
Au lieu de demander à l'utilisateur de définir un mot de passe à un moment, lui envoyer toujours un magic link par email. L'OTP wizard est déjà passwordless — étendre ce pattern à la connexion future au tenant.

**Référence** : Slack, Notion, Linear utilisent ce pattern.

### M2. SSO / OIDC depuis le tenant ROOT
Permettre de créer un espace depuis un compte ROOT déjà connecté (skip identity step). Implémenté partiellement : `skip_otp = request.user.is_authenticated and email_valid`. À étendre pour pré-remplir first_name/last_name depuis le TibilletUser ROOT.

### M3. Observabilité
- **Sentry** : capture des exceptions Celery `create_tenant_from_draft`, des 502 sur `/onboard/launch/status/`, des erreurs Nominatim.
- **Metrics** : compteur Prometheus `onboard_wizard_step_view_total{step}` + `onboard_tenant_creation_duration_seconds`.
- **Audit log** : table dédiée `OnboardAuditLog(wc_uuid, action, timestamp, ip)` pour traçabilité prod.

### M4. A/B testing flux
**Hypothèse** : "court formulaire identity en 1 page" vs "wizard 6 étapes" — lequel convertit le mieux ?

**Méthode** : feature flag (GrowthBook ou simple settings), split 50/50, mesurer le taux de complétion (`current_step == "launch"` ET `tenant_id is not None`).

### M5. Analytics du wizard (drop-off funnel)
Tracker à quelle étape les utilisateurs abandonnent. Outils : Plausible / PostHog / Matomo. Métrique clé : "step abandonnement" + "temps passé par step".

### M6. Save autosave brouillon en temps réel
Actuellement, le brouillon est sauvegardé seulement au submit de chaque step. Si l'utilisateur perd la connexion entre 2 steps, il perd les valeurs saisies du champ courant.

**Solution** : POST autosave HTMX toutes les 30s (ou sur blur) qui synchronise avec le WC.

### M7. Pré-validation IA (gentil scribe)
Au moment où l'utilisateur écrit `long_description`, un service LLM en arrière-plan suggère :
- Reformulation pour clarté.
- Détection de propos haineux (modération automatique).
- Auto-complétion du `short_description` à partir du `long_description`.

**Modèle** : Claude Haiku via API, prompt sobre. Optionnel (toggle UI "Aide IA").

### M8. Carte interactive avec recherche d'adresse intelligente
Actuellement le geocode se déclenche sur `change delay:1s`. Améliorations :
- **Suggestions au fur et à mesure** : autocomplete style Algolia Places ou Mapbox Geocoder.
- **Validation back-end** : vérifier que l'adresse renvoyée par Nominatim correspond à une vraie commune (pas du milieu de l'océan).
- **Reverse geocoding** : si l'utilisateur place le marker manuellement, remplir l'adresse depuis Nominatim.

### M9. Upload progressif (resumable uploads)
Logo (max 5 Mo) et images events : si l'utilisateur a une connexion mobile lente, l'upload peut échouer. Solution : tus.io ou Uppy resumable upload.

### M10. Templates email mobile-first + tests Litmus
Les emails OTP et "ready" sont fonctionnels mais minimalistes. Tester avec Litmus / Mailtrap sur :
- iOS Mail, Gmail mobile, Outlook web.
- Dark mode email clients.
- Accessibilité screen reader.

### M11. Choix du thème lors du wizard
Step "Personnalisation" optionnelle : choisir un skin parmi `reunion`, `faire_festival`, `htmlskin` (déjà dans `BaseBillet/templates/`). Preview live.

### M12. Stripe Connect onboarding intégré
Aujourd'hui, le tenant doit configurer Stripe après création depuis l'admin. Intégrer le flow Stripe Connect directement dans le wizard (Step "Paiements" optionnelle).

**Référence** : Substack, Calendly proposent Stripe Connect dans leur onboarding.

### M13. Mode "Try first" (espace temporaire)
Permettre de générer un espace temporaire (4h de durée de vie) sans email vérifié, pour que l'utilisateur teste l'admin avant de s'engager. Conversion vers tenant permanent en 1 clic.

### M14. Vidéo de bienvenue à la création
Step Launch : pendant les ~2 minutes de création tenant, afficher une vidéo embedded (YouTube/Vimeo non-tracking) qui explique TiBillet. Améliore la perception du temps d'attente.

### M15. Notifications push (PWA)
Si l'utilisateur ferme l'onglet pendant la création, envoyer une notification push "Votre espace est prêt" (en plus de l'email). Nécessite PWA + Service Worker.

### M16. Tests d'intégration anti-régression CI
Lancer la suite pytest onboard + Playwright E2E en CI à chaque PR. Bloquer le merge si < 90% de tests passent.

### M17. Accessibility audit avec axe-core
Passer chaque step au `axe-core` automated audit. Cible : 0 violation a11y "critical" / "serious".

### M18. Performance budget
Lighthouse audit sur les 6 steps :
- Performance ≥ 90.
- Accessibility = 100.
- Best Practices ≥ 95.
- SEO ≥ 90 (pour le hash anchor étape qui aide en partage).

### M19. Diagnostic UX (heatmaps + session recording)
Hotjar / Microsoft Clarity sur la version de prod (avec consent banner) pour comprendre où les utilisateurs s'embrouillent.

### M20. Internationalisation au-delà de FR/EN
TiBillet a une vocation outre-mer / coopérative internationale. Ajouter : ES (Amérique latine), PT (Brésil), DE (coopératives allemandes).

---

## 🟡 NICE-to-have (polish, dette technique)

### N1. Décorateur `@require_confirmed_draft`
Pattern dupliqué 6× dans `views.py` :
```python
wc = _get_or_none_wc(request)
if wc is None or not wc.email_confirmed:
    return redirect("onboard-identity")
```
À factoriser en décorateur méthode ou en helper `_get_confirmed_wc_or_redirect(request) -> (wc, redirect_or_none)`.

### N2. Refactor `events_draft` JSONField → modèle `OnboardEventDraft`
Actuellement les events brouillons sont en JSONField. C'est OK FALC mais limite :
- Pas de FK propre vers le futur Event créé.
- Pas de validation DB (juste serializer).
- Image stockée en path string vs vrai ImageField.

Refactor : créer `OnboardEventDraft(FK WaitingConfiguration, name, datetime, description, image=StdImageField)`. Migration data si nécessaire (peu probable, peu de drafts en cours).

### N3. Templatetag `is_step_done`
Au lieu de répéter les `or step == '...'` dans `progress_panel.html`, créer un templatetag :
```python
@register.simple_tag
def is_step_done(current_step, target_step):
    order = ['identity', 'verify', 'place', 'descriptions', 'events', 'launch']
    return order.index(current_step) > order.index(target_step)
```

### N4. Wizard JS extraction en module ES6
`wizard.js` mélange OTP, slug preview, carrousel dans une IIFE. Refactor en 3 modules `otp.js` / `slug-preview.js` / `carousel.js` avec un loader principal. Plus testable.

### N5. CSS extraction des variables vers `:root`
Les variables `--tb-green-*` sont définies sur `.onboard-wizard`. Les remonter en `:root` pour réutilisation ailleurs (admin, autres pages TiBillet).

### N6. Suppression du commentaire FK federation
Quand fedow_core mergera (cf. F1), retirer toutes les références "FK federation commentée" dans :
- `onboard/models.py:67-72`
- `onboard/tasks.py::create_tenant_from_draft` (bloc commenté lignes 312-328)
- Tests : décommenter `test_create_tenant_from_draft_attaches_to_invitation_federation`
- Migrations : créer `onboard/0002_add_federation_fk.py`

---

## Synthèse priorités

```
Priorité 1 (avant prod publique) :
  F1 Fedow exception → tenants pool pre-configurés
  F2 Tests Playwright E2E (3-6 scénarios)
  F3 CHANGELOG + i18n compilemessages
  S1 Heartbeat Celery
  S6 Captcha anti-abuse identity
  S7 Rate-limit identity POST
  M17 axe-core a11y audit

Priorité 2 (premier mois post-prod) :
  S2 Audit logs PII
  S4 Reprise brouillon depuis email
  S5 Preview tenant avant launch
  M3 Sentry + metrics
  M5 Analytics drop-off funnel
  M10 Tests email Litmus

Priorité 3 (3-6 mois) :
  M1 Magic link login
  M6 Autosave temps réel
  M8 Geocoder amélioré
  M12 Stripe Connect dans wizard
  M16 CI tests anti-régression
  N2 Refactor events_draft modèle

Priorité 4 (exploration) :
  M4 A/B testing
  M7 Pré-validation IA
  M11 Choix thème
  M13 Try-first temporaire
  M15 PWA notifications
  M20 i18n extended
```
