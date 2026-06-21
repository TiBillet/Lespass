# Spec 11 — C-C : le FED legacy comme cran de cascade transparent

Date : 2026-06-20 (révisée le 2026-06-20 — modèle « transparent », plus de bouton)
Statut : spec d'implémentation du lot **C-C**.
Fondé sur la lecture du code réel : `lespass-main/laboutik/views.py`
(`_payer_par_nfc`, `payer_complementaire`) et le client `fedow_connect` de
**Lespass V1** (`fedow_api.py`).

> ⚠️ **Numéros de ligne indicatifs.** `lespass-main` est en développement actif (le fichier
> `laboutik/views.py` a bougé de +70 lignes *pendant* la rédaction — cf. point 5 / doc 06 §3).
> Se référer aux **noms de fonctions**, pas aux numéros cités.

> **Principe directeur — TRANSPARENT + TEMPS RÉEL + SAFE.** Le FED legacy n'est **pas** un
> moyen de paiement à activer. C'est un **cran de la cascade**, exactement comme les monnaies
> locales. L'utilisateur et le caissier **ne font rien de spécial** : ils paient, et le système
> prend d'abord les locaux, puis le FED, **automatiquement**. Aucun bouton, aucun choix.

---

## 0. Le principe en une phrase

> À chaque paiement carte, la cascade descend **TNF → TLF (locaux) → FED (réseau, via Fedow)**,
> sans aucun geste de l'opérateur. Le solde FED est lu **en temps réel** (sans cache) et le FED
> est **débité à la validation de la vente**, jamais avant.

Trois propriétés, tenues ensemble :
- **Transparent** : le FED est un cran de cascade, pas un bouton. Personne ne le « choisit ».
- **Temps réel** : le solde FED est lu frais à chaque paiement (pas le cache 10 s).
- **Safe** : le débit FED part **à la validation** (pas d'avance), il est **fail-fast** (tout ou
  rien) et **dégradé** si Fedow ne répond pas (la vente aboutit en locaux + espèces/CB).

---

## 1. Le décor : la cascade NFC et ses deux sorties

`_payer_par_nfc` débite des **assets locaux** (`fedow_core`) dans l'ordre
`ORDRE_CASCADE_FIDUCIAIRE = TNF → TLF → FED`. **En S6, le cran FED local est vide** (pas
d'asset FED local) → la cascade locale se réduit à **TNF → TLF** sans toucher au code. **Le FED
du réseau s'insère comme le cran suivant**, juste après les locaux.

| Sortie | Condition | Ce qui se passe |
|---|---|---|
| **Couverte** | locaux + FED couvrent tout le panier | bloc atomic = **validation** : débit locaux + débit FED |
| **Complément** | il reste après locaux + FED | écran complément (espèces/CB/2ᵉ carte) ; tout est débité **à la validation finale** |

---

## 2. Le contrat HTTP (déjà présent dans `fedow_connect` V1)

**Lire le solde FED — `retrieve_by_signature(user)`** (`fedow_api.py:535`) : appel HTTP
**direct et frais**. C'est CELUI à utiliser au paiement.
> ⚠️ **Piège cache.** `get_total_fiducial_and_all_federated_token` (`:463`) lit via
> `cached_retrieve_by_signature` (cache 10 s) → **solde potentiellement périmé**. Au paiement,
> appeler `retrieve_by_signature` **direct** et calculer le dépensable FED dessus (FED + TLF du
> lieu + TLF fédérés — même logique que `get_total_fiducial`, mais sur le wallet frais). Le
> cache reste OK pour les **affichages** (consultation de carte, my_account), pas pour le débit.

**Débiter le FED — `to_place_from_qrcode(user, amount, asset_type, comment, metadata)`**
(`fedow_api.py:960`) :
- `sender = user.wallet.uuid` — **signé par la clé RSA du user** (Lespass la détient).
- `receiver = fedow_config.wallet.uuid` — le wallet de la **place** du tenant (cf. §7).
- `asset_type="EURO"` → **la cascade legacy (TLF fédérés → FED) est faite côté serveur Fedow**.
  Le POS demande un montant (centimes int), reçoit la **liste** des transactions.
- **Fail-fast** : refus total si solde insuffisant (pas de débit partiel).
- Échec (status ≠ 201) → **lève `Exception`** → toujours dans un `try/except`.

---

## 3. L'insertion — le cran FED dans la cascade

### 3.1 Lecture du FED — systématique, fraîche ; utilisation dans la cascade si besoin
Dans `_payer_par_nfc`, le solde FED est lu **systématiquement** (carte liée), via le helper
§4bis, pour **afficher le solde complet** ET alimenter la cascade. Lecture **fraîche**
(`retrieve_by_signature`, **pas** le cache).
- **Si** `total_complementaire > 0` (les locaux ne couvrent pas tout) → le FED entre dans la
  cascade : `fed_couvert = min(total_complementaire, dépensable_FED)` ; réduire
  `total_complementaire -= fed_couvert` ; **mémoriser `fed_couvert`** pour le débit. **Aucun
  débit ici** — calcul seulement.
- **Si** les locaux couvrent déjà tout → `fed_couvert = 0` (rien à débiter), mais le solde FED
  reste **affiché**.
- **Si Fedow ne répond pas / timeout** → `fed_couvert = 0` + FED « indisponible » à l'affichage,
  **dégradé silencieux**. La vente n'est jamais bloquée.

### 3.2 Débit du FED, à la validation seulement
- **Sortie « couverte »** (locaux + FED couvrent tout) → on entre dans le bloc atomic
  (validation). Débit FED `to_place_from_qrcode(fed_couvert, "EURO")` **hors atomic**, puis
  bloc atomic local (débits locaux + `LigneArticle`). Le FED est un **cran de cascade** : il
  produit **N `LigneArticle`** (1 par article couvert, comme les locaux — une `LigneArticle` a
  toujours un `price`), en **`payment_method=STRIPE_FED`** (PAS `LOCAL_EURO` : le FED réseau ≠
  monnaie locale — cf. fix compta 2026-06-21) + `asset` = uuid de l'asset FED legacy.
- **Sortie « complément »** → écran complément. `fed_couvert` est propagé (comme les données
  carte1). À la validation finale (`payer_complementaire`), on **re-lit le FED frais**
  (anti-race), on débite FED (hors atomic) puis le bloc atomic local (locaux + FED + complément).

Le FED **partiel est naturel** : il couvre ce qu'il peut, comme les locaux ; le reste va en
complément. Pas de cas spécial, pas de seuil. Et comme le débit FED ne part **qu'à la
validation**, un abandon de vente ne laisse **jamais** de débit FED orphelin (le FED n'est pas
annulable — limite 2.6).

### 3.3 Pseudo-code FALC (à quoi le code doit ressembler)

```python
# --- Dans _payer_par_nfc, après la cascade locale (PHASE 5) ---

# CRAN FED : automatique, transparent, temps réel.
# / FED tier: automatic, transparent, real-time.
fed_couvert = 0
if total_complementaire > 0 and carte_client.user is not None:
    try:
        # Lecture FRAÎCHE (sans cache) — on va peut-être débiter juste après.
        # / FRESH read (no cache).
        depensable_fed = lire_depensable_fed_frais(carte_client.user)   # retrieve_by_signature
        fed_couvert = min(total_complementaire, depensable_fed)
        total_complementaire -= fed_couvert
    except Exception:
        # Fedow injoignable → dégradé : pas de FED, on continue avec les locaux.
        # / Fedow unreachable → degraded: no FED, keep locals.
        fed_couvert = 0

# --- À la VALIDATION (ici si total_complementaire == 0, sinon dans payer_complementaire) ---
if fed_couvert > 0:
    # Débit FED HORS atomic (appel réseau ; un verrou DB pendant la latence serait un bug).
    # / FED debit OUTSIDE atomic.
    fedow_api.to_place_from_qrcode(
        user=carte_client.user, amount=fed_couvert, asset_type="EURO",
        comment=f"Vente POS {uuid_transaction}",
        metadata={"uuid_transaction": str(uuid_transaction)},
    )   # fail-fast : si le solde a baissé entre lecture et débit → Exception → on retombe en complément

with db_transaction.atomic():
    _debiter_cascade_locale(...)           # locaux (TNF/TLF)
    _creer_lignes_articles_cascade(...)    # + N LigneArticle FED (STRIPE_FED) si fed_couvert>0
    _creer_adhesions_si_besoin(...)
```

---

## 4. Temps réel & appel systématique à Fedow (point clé acté)

**On appelle Fedow à CHAQUE transaction carte — même pour un tenant V2** (décision actée
2026-06-20). On doit **afficher le solde complet de la carte (locaux + FED) à chaque fois**,
donc on lit le FED **systématiquement** (pas seulement quand les locaux manquent) :
1. **Consultation** (scan, `retour_carte`) → afficher locaux + FED.
2. **Paiement** (cascade) → solde frais pour l'affichage **et** la cascade.
3. **Succès** (après débit) → nouveau solde complet.

Lecture toujours **fraîche** (sans cache). Un tenant V2 **n'est pas autonome** de Fedow pour les
cartes du réseau. Régime = LaBoutik V1 (déjà tenu en festival). **Coût** : jusqu'à ~3 lectures
Fedow + 1 débit par vente carte avec FED → **à monitorer**. Si Fedow down → **dégradé** : locaux
+ « FED indisponible », la vente aboutit (locaux + espèces/CB).

- **Pas de cache au paiement** : `retrieve_by_signature` (direct), jamais `cached_…` (10 s).
- **Régime identique à LaBoutik V1** : V1 appelle déjà Fedow à chaque scan. Ce n'est pas un
  surcoût nouveau, c'est le même comportement — donc prouvé tenable en festival.
- **Dépendance d'uptime assumée** : un tenant V2 **n'est pas autonome de Fedow** pour les cartes
  du réseau. Si Fedow est down → **dégradé** (cascade limitée aux locaux + espèces/CB), **jamais
  de blocage**. À **monitorer** (latence/erreurs des endpoints Fedow utilisés par le POS).
- **Latence** : 1 appel HTTP de lecture par paiement carte (+ 1 appel de débit si FED utilisé).
  Timeout court ; au-delà → dégradé silencieux.

---

## 4bis. Afficher le solde complet partout (impact transversal)

« Afficher le solde complet à chaque transaction » touche **plusieurs points** qui montrent
aujourd'hui les **locaux seulement** (`retour_carte` lit `obtenir_tous_les_soldes`, docstring
« solde réel fedow_core ») :

| Point | Vue | Template | Aujourd'hui |
|---|---|---|---|
| Consultation carte | `retour_carte` | `hx_card_feedback.html` | locaux only |
| Récapitulatif client | (`obtenir_total_en_centimes`) | `hx_recapitulatif_client.html` | locaux only |
| Succès paiement | `_payer_par_nfc` / `payer_complementaire` (`soldes_apres_paiement`) | `hx_return_payment_success.html` | locaux only |
| Écran complément | `_payer_par_nfc` | `hx_complement_paiement.html` | locaux only (disponible) |

**Parade DRY (FALC) — un seul helper module-level** :
`obtenir_solde_complet_carte(carte) → {locaux, fed_centimes, total, fed_disponible}` qui :
- lit les locaux (`obtenir_tous_les_soldes`),
- si `carte.user` + place Fedow → lit le FED **frais** (`retrieve_by_signature`),
- gère le **dégradé** (`fed_disponible=False` si Fedow injoignable),
- est appelé par les **4 points** ci-dessus (zéro duplication de l'appel Fedow + du dégradé).

➡️ **Conséquence sur le périmètre C-C** : l'interop ne touche pas que la cascade de paiement,
mais **tous les affichages de solde carte** (~4 vues + ~3 templates). En C-A on copie ces vues
telles quelles (locaux only) ; en C-C on les enrichit via le helper. **Aucun impact V1** : ces
vues/templates sont `laboutik` (caisse V2) ; les tenants V1 (LaBoutik externe) ne sont pas touchés.

## 5. Sûreté : ordre des opérations et modes de panne

**Ordre anti-compensation : FED (HTTP) d'abord, atomic local ensuite — à la validation.**

| Quand ça casse | Conséquence | Traitement |
|---|---|---|
| Fedow injoignable **à la lecture** | pas de FED dans la cascade | dégradé : locaux + complément espèces/CB — **fréquent, propre** |
| Le débit FED échoue (solde baissé entre lecture et débit, fail-fast) | rien débité en local | re-render / re-calcul ; le reste passe en complément — **propre** |
| L'atomic local échoue **après** un débit FED réussi | FED débité sans `LigneArticle` | toast + **journal d'incident**, régularisation manuelle — **rarissime** (aucun réseau dans l'atomic local) |
| Abandon de la vente | rien n'est débité (FED pas encore appelé) | aucun — le débit n'est qu'à la validation |

---

## 6. Les gardes (qui passe par le cran FED)

1. **Carte liée à un user** : `carte.user is not None`. Comme Fedow et Lespass sont liés depuis
   toujours, **tout user du réseau a déjà une clé RSA et un wallet en local** → une carte liée
   est toujours signable et débitable. Carte anonyme → pas de FED, « liez votre carte » +
   complément espèces/CB.
2. **Pont carte** : carte du réseau inconnue de `CarteCashless` → résolue au scan, **sans wallet
   éphémère miroir** (§6bis).
3. **Place Fedow du tenant** présente (§7) — nécessaire pour lire ET débiter. Garantie par le
   handshake **automatique** à la création du tenant (plus d'opt-in — cf. §7).

---

## 6bis. Le pont carte — résolution sûre d'une carte legacy

La sûreté repose sur un **invariant déjà garanti par le code existant** :

> **Le wallet local d'un user porte TOUJOURS l'uuid de son wallet Fedow.**
> `get_or_create_wallet` (`fedow_api.py:580`) crée le `Wallet` local avec
> `uuid = UUID(réponse Fedow)`, et lève `« Wallet and member mismatch »` si un wallet local
> existant diverge. On ne *peut pas* fabriquer un wallet local à l'uuid faux.

**Compat des identifiants — garantie par contrat.** `card_tag_id_retrieve` renvoie un
`QrCardValidator` (`validators.py:189`) : `wallet_uuid`, `is_wallet_ephemere` (anonyme/liée),
`origin`. Et `first_tag_id` / `number_printed` sont validés à **exactement 8 caractères hex**
(`validate_hex8`, `validators.py:200-201`) → ils rentrent **toujours** dans
`CarteCashless.tag_id` / `number` (max 8). Le réseau est 8-hex partout (piège 9.31 sans objet).

Flux du pont (au scan, dans `_payer_par_nfc`) :
1. `card_tag_id_retrieve(tag_id)` → `None` ⇒ **« Carte inconnue »**.
2. `is_wallet_ephemere == False` (**liée**) : résoudre le user via `wallet_uuid` ; si
   `user.wallet` absent, `get_or_create_wallet(user)` le crée **à l'uuid legacy** (safe). Créer
   la `CarteCashless` **miroir** : `tag_id` = tag scanné, `user` résolu, `detail.origine` =
   réseau. **Aucun `wallet_ephemere`.** (Le `qrcode_uuid` n'est pas requis : POS NFC par `tag_id`.)
3. `is_wallet_ephemere == True` (**anonyme**) ⇒ « liez votre carte » + complément.

Défense en profondeur : interdire le cas 3 de `_obtenir_ou_creer_wallet` (création éphémère
locale) quand `carte.detail.origine` désigne un réseau legacy.

---

## 7. Le handshake place du tenant V2 (handshake AUTOMATIQUE — révisé 2026-06-20)

`to_place_from_qrcode` **et** `card_tag_id_retrieve` adressent le tenant via sa **place Fedow**
(`fedow_config.wallet.uuid`, clé de place). L'interop — lecture **et** écriture — exige donc que
le tenant V2 ait une **place Fedow**.

**Décision mainteneur (2026-06-20) : handshake AUTOMATIQUE, plus d'opt-in.** Chaque tenant
(V1 ET V2) est connecté au Fedow **dès sa création** : `create_place()` est appelé
automatiquement par `create_tenant` / `install.py` — **pas d'activation consciente, pas d'action
admin à coder**. Un tenant V2 a besoin de ce place pour accepter l'**asset fédéré (FED)** du
réseau ; la distinction V1/V2 ne porte donc **pas** sur « Fedow ou pas » (les deux y sont) mais
sur **où vit la monnaie locale cashless** : `fedow_core` LOCAL (V2) vs Fedow distant (V1).

**Mécanisme (vérifié, déjà actif).** `PlaceFedow.__init__` (`fedow_api.py:668`) appelle
`create_place()` automatiquement dès que `can_fedow()` est False. `create_place` (`:685`) est
**idempotent et protégé** (garde « Place already created ») et **autonome**. → **Rien à coder
pour le handshake en C-C/C-D** : il est déjà en place. Vérifié sur `lespass` : `can_fedow()=True`,
place `96e9d347…` créé à l'installation. Pas de handshake *cashless* en phase 1 (le cashless V2
est local `fedow_core`) ; `FedowAPI.handshake()` reste un placeholder.

> ⚠️ **G1 CADUC.** L'ancienne conception (« couper Fedow si V2 » : ne pas instancier `FedowAPI()`
> à la création d'un tenant V2, puis ré-activer via une action admin) était **à l'envers** et a
> été **retirée** (`create_tenant` / `install.py` / `signals.py` restaurés à l'original,
> re-validé pytest). Voir ROADMAP §1bis (C-B + C-D) et HANDOFF (MAJ 2026-06-20).

---

## 8. Front : aucune modification JavaScript

Le FED étant un **cran de cascade serveur** (pas un bouton), **il n'y a rien à ajouter côté
front** : ni bouton, ni JS, ni nouveau scan. L'écran complément (espèces/CB/2ᵉ carte) reste
inchangé — il n'apparaît que si locaux + FED ne couvrent pas tout. **Pas de changement de
comportement JS → pas de point à arbitrer avec le front.**

---

## 9. Conformité djc

- `ViewSet` explicite (pas `ModelViewSet`), serializers DRF (pas de Forms).
- Logique 100 % **serveur** (cascade + débit en Python) ; le FED ne touche pas le JS.
- HTMX server-rendered, `data-testid` / `aria-live` sur les écrans, FALC bilingue.
- Conversions montants : **centimes int** partout ; `get_total` renvoie des centimes (typé
  `Decimal`) → convertir explicitement `int(...)`, jamais via float.

---

## 10. Décisions ouvertes

- **Lecture FED fraîche** : appeler `retrieve_by_signature` direct au paiement, ou ajouter une
  variante `get_total_fiducial(..., use_cache=False)` dans `fedow_connect` (petite extension —
  à confirmer vs « client existant suffit »).
- **Double lecture FED** (au scan `_payer_par_nfc` puis re-lecture dans `payer_complementaire`) :
  deux appels Fedow pour une vente à complément. Acceptable (anti-race), mais à mesurer.
- **`comment`/`metadata`** de la transaction FED : conserver `uuid_transaction` (lien POS ↔ Fedow
  en cas de litige).
