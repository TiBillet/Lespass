# Chantier — Auth kiosk controlvanne vs flow audité laboutik

**Date** : 2026-05-05
**Statut** : 🟡 À reprendre — décision d'alignement en attente
**Branche** : `dev_vps`
**Contexte** : Review du merge `dev_vps` → `V2`. Le flow auth-bridge laboutik est audité et solide ; on regarde si controlvanne s'aligne dessus ou diverge.

---

## 1. Principe violé

> `controlvanne` ne doit pas réimplémenter la logique métier laboutik, il doit s'appuyer dessus.

Le flow d'auth hardware → session navigateur a un design audité côté laboutik (`LaBoutikAuthBridgeView`). Mike a fait un design parallèle pour la tireuse (`AuthKioskView` + `KioskTokenView`) avec des manques de sécurité.

---

## 2. Le flow laboutik (référence audité)

`laboutik/views.py:8501-8614` — `LaBoutikAuthBridgeView` + `BridgeThrottle`

**Une seule étape** :

```
Navigateur (Cordova WebView ou Chromium) POST /laboutik/auth/bridge/
  Body: api_key=<key>   ← dans le BODY, pas le header (bypass CORS preflight)

→ BridgeThrottle (10 req/min par IP)
→ LaBoutikAPIKey.objects.get_from_key()
  - 401 vide si clé absente/invalide/révoquée (pas de side-channel)
  - 400 si clé V1 sans user lié (legacy)
→ if not term_user.is_active: 401  (révocation)
→ login(request, term_user)         (Django auth natif)
→ session.set_expiry(60*60*12)      (12h)
→ HttpResponseRedirect('/laboutik/caisse/')  (302 + Set-Cookie sessionid)
```

**Discovery claim associée** (`discovery/views.py:88-92, 109-116`) → `_create_laboutik_terminal()` (`discovery/views.py:159-201`) crée un `TermUser` (`espece=TE`, `terminal_role=LB|KI`) **et** une `LaBoutikAPIKey(user=term_user)`. La clé est liée à un user.

---

## 3. Le flow controlvanne (Mike)

`controlvanne/viewsets.py:670-803` — `AuthKioskView` + `KioskTokenView`

**Deux étapes** (justifié : Pi Python pilote Chromium subprocess, donc cookie à transférer) :

```
ÉTAPE 1 — Pi POST /controlvanne/auth-kiosk/
          Header Authorization: Api-Key <TireuseAPIKey>

  HasTireuseAccess.has_permission()  ← valide la clé
  request.session.create()           ← session ANONYME (pas de User)
  request.session["controlvanne_authenticated"] = True  ← flag custom
  kiosk_token = uuid4()
  cache.set(f"kiosk_token:{token}", True, timeout=300)
  return JSON {session_key, kiosk_token}

  Le Pi écrit l'URL avec ?kiosk_token=... dans /tmp/tibeer_kiosk_url

ÉTAPE 2 — xinitrc lance Chromium sur /controlvanne/kiosk-token/<token>/?next=<kiosk_url>
          (KioskTokenView, AUCUNE permission, AUCUNE auth_classes)

  cache.get(f"kiosk_token:{token}")  ← consomme le token
  request.session["controlvanne_authenticated"] = True  ← sur la session de Chromium
  request.session.save()              ← Set-Cookie via SessionMiddleware
  return HttpResponse(meta-refresh → next_url)  ← 200 + redirect HTML
```

**Discovery claim associée** (`discovery/views.py:93-107`) → crée `TireuseAPIKey.objects.create_key(...)` **sans `TermUser`, sans user lié**. Commentaire ligne 94 : "Flow Tireuse INCHANGÉ pour cette phase" → dette reconnue.

---

## 4. Tableau de comparaison

| Critère | laboutik (audité) | controlvanne (Mike) |
|---|---|---|
| **Sujet de session** | `TermUser` (`espece=TE`, `terminal_role=LB`) | **Anonyme** — flag `controlvanne_authenticated=True` |
| **Mécanisme auth** | `django.contrib.auth.login()` natif | flag custom dans `request.session` |
| **Discovery claim** | crée `TermUser` + `LaBoutikAPIKey(user=term_user)` | crée `TireuseAPIKey` **sans user** |
| **Check révocation** | `if not term_user.is_active: 401` (8595) | ❌ **Aucun** — flag jamais re-vérifié contre la clé |
| **Throttling brute-force** | `BridgeThrottle = 10/min` | ❌ **Aucun** sur `/auth-kiosk/` |
| **Durée session** | `set_expiry(60*60*12)` = 12h | défaut Django = 2 semaines (`SESSION_COOKIE_AGE`) |
| **Logs sécurité** | brute-force / invalid / revoked / success différenciés | générique "Auth kiosk OK" |
| **Étapes** | 1 POST → 302 + cookie | 2 étapes : POST → token → GET → cookie |
| **Cache du token** | N/A | `cache.set(...)` — ⚠️ piège prod multi-worker si LocMemCache |
| **XSS reflective** | redirect statique `/laboutik/caisse/` | ⚠️ `next_url` injecté en f-string (ligne 791-803) — bénin si Pi maîtrise l'URL |

---

## 5. Pourquoi 2 étapes côté controlvanne ?

C'est **légitime** : le Pi est un script Python qui parle à `/auth-kiosk/` via `requests`, mais c'est **Chromium subprocess** qui doit recevoir le cookie. On ne peut pas transférer un cookie de `requests` à Chromium directement.

Côté laboutik c'est plus simple parce que c'est le **navigateur lui-même** (Cordova WebView ou Chromium via formulaire HTML natif) qui POST au bridge — donc c'est lui qui reçoit le Set-Cookie.

Le mécanisme du token UUID + cache 5 min est l'astuce pour transférer l'autorisation du process Pi vers le navigateur. **Le détour est OK, ce qui ne va pas c'est le contenu du token et l'absence de TermUser.**

---

## 6. Les 5 manques de sécurité concrets

### 6.1 Pas de `TermUser`
La session controlvanne est anonyme → impossible de tracer "quel terminal a fait quoi" en post-mortem. Côté laboutik on a `request.user = TermUser` partout en aval (logs, permissions, audit).

### 6.2 Pas de throttling sur `/auth-kiosk/`
Quelqu'un qui a sniffé une clé peut spammer 10 000 req/s sans freinage. Laboutik = 10/min.

### 6.3 Pas de check is_active
Si l'admin désactive la `TireuseAPIKey` (ou ajoute un flag révoqué sur le futur `TermUser`), les sessions déjà ouvertes restent valides 2 semaines (durée par défaut Django). Le flag `controlvanne_authenticated=True` n'est jamais re-vérifié contre la clé.

### 6.4 Durée session non bornée
Laboutik force 12h via `set_expiry(60*60*12)`. Controlvanne laisse `SESSION_COOKIE_AGE` (2 semaines). Pour un device qui tourne 24/7 dans un bar, 2 semaines est trop long.

### 6.5 Cache du token = piège prod multi-worker
`cache.set(f"kiosk_token:{token}", True, timeout=300)` — si le backend cache est `LocMemCache` (default Django sans config), **le token créé par worker Daphne A ne sera pas trouvé par worker Gunicorn B**. Crash silencieux 403 "Token invalide ou expiré". Faut Redis ou PgCache.

---

## 7. Asymétrie côté `discovery/views.py`

C'est là que la dette se voit le plus :

```python
# Lignes 88-92 — Laboutik V2
api_key_string = _create_laboutik_terminal(pairing_device)
# → crée TermUser + LaBoutikAPIKey(user=term_user)

# Lignes 109-116 — Kiosque
api_key_string = _create_laboutik_terminal(pairing_device)
# → idem (réutilise le helper Laboutik)

# Lignes 93-107 — Tireuse
TireuseAPIKey.objects.create_key(name=...)
# → pas de TermUser, pas de user lié
# Commentaire : "Flow Tireuse INCHANGÉ pour cette phase"
```

L'asymétrie est volontaire et reconnue comme dette. À résorber.

---

## 8. Comment l'aligner sur laboutik

### 8.1 Phase claim discovery
`discovery/views.py:93-107` — créer un `TermUser(terminal_role=ROLE_TIREUSE, espece=TE)` lié à la `TireuseAPIKey`. Symétrie avec `_create_laboutik_terminal`. Modèle déjà supporté (`AuthBillet/models.py` a `ROLE_TIREUSE`).

Variante : généraliser `_create_laboutik_terminal` en `_create_terminal(pairing_device)` qui crée le bon type de clé selon `terminal_role`.

### 8.2 Phase auth-kiosk
Refondre comme :

```python
class AuthKioskView(APIView):
    permission_classes = [HasTireuseAccess]
    throttle_classes = [BridgeThrottle]   # ← partager avec laboutik

    def post(self, request):
        # HasTireuseAccess a déjà validé la clé
        api_key = ...  # via la lib djangorestframework-api-key
        term_user = api_key.user
        if not term_user or not term_user.is_active:
            return HttpResponse(status=401)

        login(request, term_user)              # ← login Django natif
        request.session.set_expiry(60*60*12)   # ← 12h aligné laboutik

        # Le détour token reste nécessaire car Pi != Chromium
        # Le token = pointeur vers la session déjà ouverte
        kiosk_token = uuid4()
        cache.set(
            f"kiosk_token:{kiosk_token}",
            request.session.session_key,
            300,
        )
        return Response({"kiosk_token": kiosk_token})


class KioskTokenView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request, token):
        session_key = cache.get(f"kiosk_token:{token}")
        if not session_key:
            return HttpResponseForbidden()
        cache.delete(f"kiosk_token:{token}")

        # Charger la session ouverte par AuthKioskView, transférer son user
        # vers la session navigateur courante
        from django.contrib.sessions.backends.db import SessionStore
        store = SessionStore(session_key=session_key)
        user_id = store.get('_auth_user_id')
        if not user_id:
            return HttpResponseForbidden()

        term_user = TermUser.objects.get(pk=user_id)
        if not term_user.is_active:
            return HttpResponseForbidden()

        login(request, term_user)
        request.session.set_expiry(60*60*12)

        next_url = iri_to_uri(request.GET.get("next", "/controlvanne/kiosk/"))
        return HttpResponseRedirect(next_url)
```

### 8.3 Bénéfices
- Une seule notion de session (`TermUser`) au lieu d'un flag custom
- Révocation immédiate via `term_user.is_active = False`
- Throttling, audit, durée bornée alignés avec laboutik
- `request.user` exploitable dans les vues kiosk (logs, permissions)
- `_verifier_authentification_kiosk()` (`controlvanne/viewsets.py:830-870`) devient `request.user.is_authenticated and isinstance(request.user, TermUser)` — plus de flag custom
- `iri_to_uri(next_url)` règle le problème XSS reflective (l'IDE PyCharm flagguera)

### 8.4 Dépendance
La 8.2 dépend de la 8.1 : sans `TermUser` lié à la `TireuseAPIKey`, on ne peut pas faire `login()`. Donc commencer par discovery.

---

## 9. Fichiers à ouvrir dans PyCharm

```
laboutik/views.py:8501-8614          — LaBoutikAuthBridgeView + BridgeThrottle (référence)
discovery/views.py:88-126             — routage par terminal_role (claim)
discovery/views.py:159-201            — _create_laboutik_terminal helper
controlvanne/viewsets.py:670-727      — AuthKioskView (Mike)
controlvanne/viewsets.py:736-803      — KioskTokenView (Mike)
controlvanne/viewsets.py:805-870      — _verifier_authentification_kiosk
controlvanne/permissions.py:23-60     — HasTireuseAccess
controlvanne/models.py:60-85          — TireuseAPIKey (sans user lié)
AuthBillet/models.py                  — TermUser, ROLE_TIREUSE, ROLE_LABOUTIK, ROLE_KIOSQUE
```

---

## 10. Recommandation

Comme le chantier billing : **alignement sur laboutik est la cible**, mais c'est une session dédiée à programmer après l'exploration complète de `dev_vps`.

**Minimum viable pour le merge** (si on ne veut pas dériver) :
- Ajouter `BridgeThrottle` (ou équivalent) sur `AuthKioskView`
- Borner la session avec `set_expiry(60*60*12)`
- Escaper `next_url` avec `iri_to_uri()` ou whitelist
- Documenter explicitement la limite "cache partagé requis en prod multi-worker" dans README

À décider avec le mainteneur.