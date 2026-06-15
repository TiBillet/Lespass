# Recherche 04 — Scénario S4 : import de Fedow tel quel (« strangler fig »)

Date : 2026-06-10
Proposition mainteneur : importer l'app Fedow **telle quelle** dans Lespass,
migrer la base SQLite vers PostgreSQL **sans transformation**, basculer le DNS
du domaine Fedow vers Lespass. Aucune mise à jour côté LaBoutik V1 ni côté
webhooks Stripe — ils continuent d'appeler les mêmes URLs. Puis désamorcer
l'API legacy de l'intérieur, en remplaçant progressivement les appels HTTP de
`fedow_connect` par des appels en DB directe.

C'est le pattern **strangler fig** : absorber le service sans toucher à son
contrat, puis l'étrangler appel par appel.

---

## 1. Pourquoi ce scénario surclasse S1/S2/S3

| Problème des autres scénarios | En S4 |
|---|---|
| B3 — graphe FED indécoupable | **Disparaît** : les données ne sont pas découpées, elles déménagent en bloc avec le code qui les interprète |
| B4 — sémantique débit/crédit V1≠V2 à l'import | **Disparaît** : même code, mêmes données, zéro transformation |
| B6 — autonomie wallet sans Fedow | **Disparaît** : le moteur EST dans Lespass |
| B7 — instance `.re` servie par le même Fedow | **Neutralisé** : l'API HTTP reste exposée sur le même domaine, `.re` continue de l'appeler sans rien savoir du déménagement |
| Double réseau FED (S2) | **Disparaît** : un seul moteur, un seul réseau |
| Dispatch par tenant (S1/S2) ou par asset (S3) | **Disparaît** : pas de dual-run, pas de branches V1/V2 dans les vues |
| Cascade POS hybride + double écriture cartes (S3) | **Disparaît** : un seul registre |
| Gate « migrer un tenant = migrer sa caisse » (S3) | **Disparaît** : LaBoutik V1 continue en HTTP, indéfiniment si besoin |
| Bugs V2 de l'audit (B1, M1-M9) | **Plus bloquants** : le code V2 n'est plus la base déployée ; il devient la *cible de refactoring* du désamorçage |
| Garde-fous métier V1 disparus en V2 (M5) | **Conservés** : les assertions de `Transaction.save()` voyagent avec le code |

Les nouveaux tenants deviennent simplement de nouvelles `Place` dans le même
moteur — ils rejoignent nativement le réseau FED existant (la question décisive
de S2 vs S3 est résolue par construction).

---

## 2. Les points durs vérifiés dans le code (2026-06-10)

### 2.1 `AUTH_USER_MODEL` — chirurgie obligatoire mais bornée ✂️
Fedow déclare `AUTH_USER_MODEL = 'fedow_core.FedowUser'`
(`fedowallet_django/settings.py:213`). Un projet Django n'a qu'un seul user
model : impossible d'importer « tel quel » sur ce point. Sites concernés
vérifiés : FK `settings.AUTH_USER_MODEL` sur CheckoutStripe.user (models.py:63),
Place.admins (l.1095), Card.user, OrganizationAPIKey.user, + 1
`get_user_model()` (l.1192). **Correction** : FedowUser devient un modèle
ordinaire (plus swappable), FKs en `'fedow_core.FedowUser'` littéral, et
**migrations régénérées à neuf** (les anciennes référencent le swappable).
Conséquence ETL : import par dumpdata/loaddata ou script, pas par replay des
migrations Fedow. Le rapprochement FedowUser ↔ TibilletUser (par email) n'est
PAS nécessaire au déménagement — il se fera progressivement au désamorçage.

### 2.2 Secrets chiffrés — re-chiffrement à l'ETL 🔑
Vérifié dans `fedow_core/utils.py` :
- clés privées RSA chiffrées avec **le SECRET_KEY de Fedow**
  (`BestAvailableEncryption(settings.SECRET_KEY)`, l.110, déchiffrement l.124) ;
- dérivation PBKDF2 avec `settings.SALT` (l.76) ;
- clés Stripe + apikey cashless chiffrées **Fernet** avec le FERNET_KEY de Fedow
  (models.py:873-902).
**Correction** : soit l'ETL déchiffre avec les clés Fedow et re-chiffre avec
celles de Lespass, soit on ajoute des settings dédiés (`FEDOW_SECRET_KEY`,
`FEDOW_FERNET_KEY`, `FEDOW_SALT`) et on adapte utils.py. Les API keys de
LaBoutik (djangorestframework-api-key) sont hashées indépendamment du
SECRET_KEY → **elles survivent à l'import telles quelles**, c'est ce qui
garantit le « zéro mise à jour côté LaBoutik ».

### 2.3 Conflit de versions : stripe ^15 (Fedow) vs ^12 (Lespass) ⚠️
Trois versions majeures d'écart sur la lib Stripe — le seul vrai chantier de
dépendances. Soit upgrade de Lespass vers stripe 15 (touche PaiementStripe,
campagne de tests dédiée), soit adaptation des appels Fedow à la v12.
Autres deps vérifiées OK : django ^4.2 des deux côtés, DRF ^3.14,
djangorestframework-api-key ^3, django-solo compatible.

### 2.4 Routage django-tenants + middleware 🌐
- Le domaine Fedow doit exister dans `Customers.Domain` comme **domaine
  primaire d'un tenant dédié** (sinon `CanonicalDomainRedirectMiddleware` —
  vérifié : redirige les GET/HEAD vers le domaine primaire — casserait les
  GET de l'API LaBoutik par des 301).
- Servir les URLs Fedow sur ce hostname : middleware host-based simple qui pose
  `request.urlconf` (django-tenants ne fait nativement que public vs tenant).
- Les modèles Fedow vont en SHARED_APPS (schéma public) : aucune notion de
  tenant dans le moteur, accessible depuis tous les schémas pour le désamorçage.

### 2.5 Cache partagé — `cache.clear()` nucléaire 💣
Vérifié : `Federation.save()` et 2 autres méthodes font `cache.clear()`
(models.py:837, 874, 895). Dans le Redis partagé de Lespass, cela viderait
**tout** le cache du site à chaque sauvegarde de fédération. Correction simple :
alias de cache dédié (`CACHES['fedow']`) ou invalidation ciblée par clés.

### 2.6 Signaux sans garde `raw` — duplication à l'ETL 💣
Le signal post_save d'Asset crée Token + transaction FIRST, et la garde
loaddata est commentée (audit dimension 1). Un `loaddata` déclencherait des
doublons. Correction : réactiver la garde (`if raw: return`) avant l'ETL.

### 2.7 PostgreSQL vs SQLite : la concurrence change de régime
SQLite sérialise les écritures (WAL, un seul writer) — c'est ce qui limitait la
casse des courses existantes. PostgreSQL apporte de la vraie concurrence : le
choix du `previous_transaction` (tête de chaîne) non verrouillé pourrait
**augmenter le taux de forks** (déjà ~320 tolérés). Mitigation simple au
moment du déménagement : `select_for_update` sur la tête de chaîne par asset,
ou acter que les forks restent tolérés comme aujourd'hui. Le patch F() du
DRIFT est lui déjà dans le code importé.

### 2.8 Couplage d'uptime — le vrai prix du scénario 🏗️
Aujourd'hui Fedow standalone est petit, stable, isolé : un déploiement raté de
Lespass n'empêche personne de payer sa bière. Après S4, **chaque déploiement /
panne de Lespass touche le réseau cashless entier** (toutes les caisses
LaBoutik V1 du réseau). À évaluer : pratique de déploiement zéro-downtime,
fenêtres de deploy hors événements, monitoring dédié des endpoints Fedow.
C'est le principal argument *contre* S4 — un argument d'exploitation, pas de
code.

---

## 3. Le plan S4 en trois temps

### Temps 1 — Import de l'app (chantier de code, sans bascule)
1. Copier `fedow_core` (Fedow) dans Lespass sous un nom d'app distinct du
   prototype V2 — proposition : **`fedow_legacy`** (évite la collision avec le
   futur refactor et dit ce que c'est). Adapter : FedowUser non-swappable,
   settings secrets dédiés, cache alias, garde `raw` sur les signaux,
   migrations à neuf, urlconf host-based.
2. Unifier la dépendance stripe (^12 vs ^15).
3. **Tests de contrat** : transformer `fedow_api_documentation.md` + les flux
   réels de LaBoutik en suite de tests d'API (mêmes headers, signatures RSA,
   API keys) — c'est le filet de sécurité de toute la suite. La couverture de
   tests du Fedow standalone est faible (TESTS.md) : ces tests de contrat sont
   le prérequis de la bascule.
4. ETL SQLite → PostgreSQL rejouable : dumpdata/loaddata ou script ORM,
   re-chiffrement des secrets, vérifications d'intégrité (comptages, somme des
   Token.value, spot-check des hash). Répétable à volonté en staging.

### Temps 2 — La nuit de bascule (réversible)
1. Prérequis : drift=0 confirmé (reconcile_tokens passé en prod cette nuit),
   TTL DNS abaissé à l'avance.
2. Gel du Fedow standalone (lecture seule) → ETL final → tests de contrat
   contre Lespass → bascule DNS.
3. Rollback : re-pointer le DNS vers le standalone (gardé au chaud) ; toute
   écriture faite côté Lespass pendant la fenêtre d'observation doit être
   re-synchronisée — d'où une fenêtre courte, de nuit, hors événements.
4. Stripe : les webhooks ratés pendant la fenêtre sont re-livrés par Stripe
   (retries ~72h) → pas de perte.

### Temps 3 — Désamorçage (incrémental, sans échéance)
1. Flux par flux, remplacer les appels HTTP de `fedow_connect` par des appels
   Python directs vers `fedow_legacy` (en réutilisant d'abord ses
   serializers/validators : même logique, zéro régression). L'HTTP reste le
   fallback instantané de chaque étape.
2. À chaque flux désamorcé, refactorer vers la cible FALC : c'est ICI que le
   prototype V2 (`lespass-main/fedow_core/services.py`) sert de **plan
   directeur** (pattern services, centimes, exceptions) — corrigé des findings
   de l'audit (B1, M1-M9).
3. Rapprochement progressif FedowUser↔TibilletUser, Place↔Client,
   Card↔CarteCashless — par flux, jamais en big-bang.
4. L'instance `.re` et les LaBoutik V1 restent en HTTP aussi longtemps que
   nécessaire — leur migration est découplée de tout le reste.

---

## 4. Verdict

**S4 > S3 > S2 > S1.** S4 est le seul scénario qui supprime le problème du
dual-run au lieu de l'organiser : un seul moteur, un seul réseau FED, zéro
changement client, et une migration de données « bête » (code et données
voyagent ensemble) au lieu d'une traduction sémantique risquée. Le travail
risqué se concentre sur UNE nuit réversible, préparée par des tests de
contrat rejouables ; tout le reste est du refactoring incrémental.

Les contreparties à assumer :
1. **Couplage d'uptime** Lespass ↔ réseau cashless (§ 2.8) — la seule vraie
   objection, à traiter par les pratiques de déploiement.
2. Un chantier de dépendances stripe ^12→^15.
3. Du code non-FALC entre temporairement dans le repo (sous le nom
   `fedow_legacy`, avec interdiction d'y construire du neuf : le neuf se
   construit dans le refactor).

## 5. Questions ouvertes pour le mainteneur

1. **Nom de l'app importée** : `fedow_legacy` (proposition, distincte du futur
   `fedow_core` refactoré) ou `fedow_core` directement ?
2. **Stripe** : upgrade Lespass vers ^15 ou downgrade des appels Fedow vers ^12 ?
3. **Uptime** : valider la stratégie de déploiement (rolling/zero-downtime,
   fenêtres hors événements) avant la bascule.
4. **fedow_dashboard** : importé aussi (continuité d'exploitation) ou remplacé
   par des vues Unfold dans l'admin Lespass ?
5. Le tenant dédié au domaine Fedow : quel `Client` (catégorie, schéma) ?
