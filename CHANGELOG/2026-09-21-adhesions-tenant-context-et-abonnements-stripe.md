# Adhésions : objets déracinés, statuts et abonnements Stripe / Memberships: detached objects, statuses and Stripe subscriptions

**Date :** 2026-09-21
**Migration :** Non

## Resume / Summary

**Quoi / What :** session de relecture du pull du 18/09, qui a mis au jour une
famille de bugs autour des adhésions — tous invisibles, aucun ne levant
d'exception.

- **Corruption possible** : les cartes d'adhésion appelaient des méthodes de
  `Membership` au rendu, donc hors du `tenant_context` qui les avait chargées.
  `is_valid()` peut finir par un `save()` : l'`UPDATE` partait sur le schéma du
  lieu affiché, avec une PK entière.
- **Fonctionnalité morte** : le bouton « arrêter le prélèvement » ne s'affichait
  pour personne, les gabarits comparant `status == 'A'` (= `ONCE`) là où ils
  visaient `AUTO` (= `'O'`).
- **Résiliation** : arrêter son prélèvement coupait l'adhésion sur-le-champ, y
  compris au comptoir, alors que la période était payée.
- **Annulation admin** : elle ne résiliait jamais l'abonnement Stripe, et un
  prélèvement ultérieur pouvait réactiver l'adhésion annulée.
- **Signaux** : `ResourceProduct` manquait dans `PROXYS_PRODUCT` depuis juin —
  archiver une ressource ne la dépubliait pas.

/ Review of the 18/09 pull. Memberships read inside a tenant_context but rendered
outside it could write to the wrong schema; the cancel-subscription button was
never displayed; cancelling cut access immediately despite a paid period; admin
cancellation never cancelled the Stripe subscription; ResourceProduct was missing
from PROXYS_PRODUCT.

**Pourquoi / Why :** les pages `/my_account/` agrègent les adhésions de plusieurs
lieux. Chaque lieu est lu dans son `tenant_context`, mais le gabarit est rendu
après en être sorti : tout appel de méthode s'exécute alors sur le mauvais schéma.
Le reste découle de constantes comparées en dur (`ONCE, AUTO = 'A', 'O'`) et d'une
annulation administrative qui ne parlait pas à Stripe.

---

## 1. Objets sortis d'un `tenant_context` : lire, jamais appeler

**Quoi :** les vues calculent désormais dans le `with` et posent des attributs
(`est_valide`, `date_fin_engagement`, `origin`) ; les gabarits ne lisent que ces
attributs. Un test statique interdit tout appel de méthode sur `membership` dans
les cartes.

**Pourquoi :** `is_valid()` → `get_deadline()` → `set_deadline()` se termine par
`self.save()`. Hors contexte, cet `UPDATE ... WHERE id = <entier>` part sur le
schéma courant et peut écraser l'adhésion d'un autre membre, ou créer une fiche
fantôme. `get_iteration_end_date()` ne sauve pas mais lit le fuseau du mauvais
lieu, décalant une fin d'engagement d'un jour.

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `est_valide` et `date_fin_engagement` posés dans les deux boucles ; `Configuration.get_solo()` sorti de la boucle interne |
| `ApiBillet/views.py` | `CancelSubscription` pose `est_valide`, `origin`, `date_fin_engagement` et recalcule `est_valide` après le passage en `CANCELED` |
| `pages/templates/.../membership_card.html` (V2 + classic), `V2/vues/compte/index.html` | 6 appels `is_valid` / 8 `get_deadline` / 6 `get_iteration_end_date` remplacés par des attributs |
| `tests/PIEGES.md` | piège **9.114** |

## 2. `ONCE, AUTO = 'A', 'O'` : le bouton qui ne s'affichait jamais

**Quoi :** propriété `est_renouvellement_auto` sur `Membership`, utilisée par les
deux cartes à la place de `status == 'A'`.

**Pourquoi :** `'A'` est `ONCE`. La condition du bouton exigeait `status == 'A'`
**et** un `stripe_id_subscription` — or `BaseBillet/triggers.py` pose l'un et
l'autre en même temps que `AUTO`. Les deux conditions étaient donc exclusives :
`CancelSubscription` était inatteignable depuis l'interface. Le badge « Paiement
récurrent » s'affichait symétriquement à l'envers.

Bug déjà décrit dans `CHANGELOG/2026-09-18-tests-cancel-subscription-et-bouton-jamais-affiche.md`.

## 3. Résilier n'est pas expirer

**Quoi :** `is_valid()` distingue les deux annulations — `ADMIN_CANCELED` coupe
immédiatement, `CANCELED` court jusqu'à la deadline. `laboutik/views.py` n'exclut
plus `CANCELED` du scan de carte.

**Pourquoi :** la résiliation pose `cancel_at_period_end=True` chez Stripe : la
période payée court jusqu'à son terme. TiBillet disait le contraire et retirait
l'adhésion au comptoir dès la résiliation. Les deux statuts ne sont pas alignés à
dessein : l'annulation admin archive la fiche et peut émettre un avoir, laisser
l'accès reviendrait à offrir l'adhésion.

Non modifiés, et c'est voulu : `max_per_user` et la recherche d'adhésion existante
excluent les annulées en SQL — résilier puis ré-adhérer reste possible, avec une
nouvelle fiche.

## 4. Annulation admin et abonnement Stripe

**Quoi :** la modale d'annulation propose de résilier l'abonnement, uniquement sur
une adhésion en prélèvement automatique, case cochée par défaut. Une garde dans
`BaseBillet/triggers.py` empêche un paiement de réactiver une adhésion
`ADMIN_CANCELED`.

**Pourquoi :** l'annulation ne parlait pas à Stripe : le prélèvement continuait, et
le webhook `invoice.paid` retrouvait la fiche puis la repassait en `AUTO` avec une
nouvelle échéance. La garde est le filet quand l'appel à Stripe échoue — cet échec
est volontairement non bloquant, donc silencieux.

La garde conserve `last_stripe_invoice` (seule déduplication du webhook), ne lève
jamais (le trigger avale les exceptions, la ligne resterait `PAID` sans passer
`VALID`) et retourne `membership` (l'appelant enchaîne sur `set_deadline()`). Le
reste de `trigger_A` suit son cours, le paiement étant réel : reçu, vente envoyée à
LaBoutik, ligne validée. Une récompense wallet peut être créditée — assumé, et
signalé dans l'alerte Sentry plutôt que traité par du code supplémentaire.

## 5. `CancelSubscription` rend le gabarit du skin courant

**Quoi :** les six chemins passent par `gabarit_skin()` au lieu d'un chemin
`pages/classic/...` en dur.

**Pourquoi :** invisible tant que le bouton ne s'affichait pas ; dès le point 2
appliqué, un clic depuis le skin V2 aurait remplacé la carte V2 par une carte
Bootstrap classic (`hx-swap="outerHTML"`).

**Effet sur les tests :** l'alerte d'erreur est une `.callout--erreur` en V2 et une
`.alert-danger` en classic. Les assertions E2E ciblent désormais `[role="alert"]`,
identique dans les deux skins.

## 6. `ResourceProduct` dans `PROXYS_PRODUCT`

**Quoi :** ajout du proxy à la liste (`BaseBillet/models.py`).

**Pourquoi :** les signaux Django sont émis avec la classe exacte du `save()`. Le
proxy, créé en juin, n'était connecté à aucun des quatre receivers : archiver une
ressource depuis l'admin ne la dépubliait pas, et le poids d'apparition n'était pas
posé à la création. Les deux autres receivers restent inertes pour cette catégorie.

## 7. WebSocket LaBoutik

**Quoi :** `ws-connect` conditionné à la présence d'un point de vente ;
l'indicateur ne passe au vert qu'à la réception du pong ; la latence utilise un
horodatage réel ; garde d'installation des listeners.

**Pourquoi :** l'écran d'attente de la carte primaire n'a pas de PV et produisait
`/ws/laboutik//`, donc `ValueError: No route found` et une reconnexion permanente.
L'indicateur passait au vert à l'**envoi** du ping — une socket ouverte sur un
consumer muet restait verte. `client_ts: 1000` en dur affichait une latence de
~1,7×10¹² ms. La garde des listeners s'appuyait sur l'état de la socket, que
`wsClose` remet à `null` : un swap pendant une coupure les dupliquait.

## 8. Page Réseau : suppression assumée du filtre par type de lieu

**Quoi :** retrait des résidus JS/CSS laissés par le commit du 15/09, et
allègement de l'enrichissement côté vue —
`_enrichir_explorer_data_avec_type_et_distance` devient
`_enrichir_explorer_data_avec_distance`.

**Pourquoi :** le filtre avait été retiré du front, mais le badge de type et son
code de support étaient restés, alimentés par une donnée qui n'existait plus. Sans
consommateur, la requête sur `Client` devenait inutile : une requête SQL de moins
par chargement de la page.

## 9. Fixtures controlvanne : le `Terminal` oublié

**Quoi :** les trois fixtures qui nettoient le `PointDeVente` auto-créé nettoient
aussi le `Terminal`.

**Pourquoi :** le signal `post_save` de `TireuseBec` crée les deux, tous deux
uniques sur `name`, et aucun n'est supprimé avec la tireuse. Chaque run laissait un
`Terminal` orphelin et le suivant échouait en `UniqueViolation` — la suite
oscillait entre 5 et 11 échecs selon les exécutions.

---

## Tests

Tous vérifiés par mutation : chaque test a été vu échouer sur une altération
volontaire du code qu'il protège.

| Fichier / File | Couvre / Covers |
|---|---|
| `tests/pytest/test_membership_gabarits_attributs.py` | garde statique contre les appels de méthode en gabarit ; fuseau de la fin d'engagement ; absence de N+1 ; rendu réel de `/my_account/membership/` |
| `tests/pytest/test_membership_resiliation_fin_de_periode.py` | résiliée-en-cours valide, résiliée-échue invalide, annulation admin immédiate, ré-adhésion possible |
| `tests/pytest/test_admin_annulation_abonnement_stripe.py` | case selon le statut, `cancel_at_period_end`, pas d'appel si décochée, échec Stripe non bloquant, garde du trigger |
| `tests/pytest/test_signaux_proxys_product.py` | archiver une ressource la dépublie |
| `tests/e2e/test_membership_recurring_cancel.py` | réécrit sur une vraie adhésion `AUTO` : garde le bouton par construction |

## Comment tester / How to test

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```
