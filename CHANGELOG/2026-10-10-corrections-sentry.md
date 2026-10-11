# Corrections d'erreurs Sentry / Sentry error fixes

**Date :** 2026-10-10
**Migration :** Oui — `BaseBillet/migrations/0229_alter_event_full_url.py`
(`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas`)

## Resume / Summary

### 1. Nom d'evenement long → erreur 500 (BILLETTERIE-COOP-T7)

**Quoi / What :** `Event.full_url` passe de 200 (defaut de `URLField`) a 500 caracteres.
/ `Event.full_url` goes from 200 (`URLField` default) to 500 characters.

**Pourquoi / Why :** `Event.save()` construit `https://<domaine>/event/<slug>/`. Avec un nom
d'environ 140 caracteres ou plus, l'URL depassait 200 et PostgreSQL refusait l'enregistrement
(`DataError: value too long for type character varying(200)`). Agrandir un `varchar` sous
PostgreSQL ne reecrit pas la table : migration rapide sur chaque lieu.
/ `Event.save()` builds the full URL; with a ~140+ character name it exceeded 200 and the insert failed.

### 2. Remise en banque d'un solde vide (BILLETTERIE-COOP-TR + FEDOW-DJANGO-4Z)

**Quoi / What :** dans la fiche d'un asset (admin), le bouton « Valider le retour en banque »
n'apparait que si le solde du lieu est positif. Sinon : « Rien a remettre en banque ».
Si Fedow refuse quand meme (« Not enough token »), l'admin voit un message lisible et
l'evenement est journalise en `warning`.
/ The bank deposit button only shows for a positive balance; a Fedow "Not enough token"
refusal now shows a readable message and is logged as a warning.

**Pourquoi / Why :** Fedow liste aussi les lieux dont le token est a 0 (apres une remise, le
token reste en base). Le bouton etait propose sur ces lignes, Fedow refusait, et l'admin voyait
le dict brut `{'non_field_errors': [...]}`. Chaque clic creait une erreur Sentry des deux cotes.
/ Fedow lists 0-balance places too; the button was offered on them and every click raised errors.

### 3. Reservation gratuite confirmee trop tard : compte jamais active (BILLETTERIE-COOP-TP)

**Quoi / What :** quand un visiteur confirme son email trop tard et que sa reservation gratuite
est annulee (evenement complet), son compte est maintenant bien active et il est connecte.
Le message d'annulation s'affiche toujours. Plus d'erreur journalisee dans Sentry.
/ When a late email confirmation cancels a free booking, the account is now activated and
logged in; the cancellation message is still shown; no more Sentry error.

**Pourquoi / Why :** le signal `activator_free_reservation` (pre_save du `TibilletUser`) levait un
`ValueError` pour transporter son message. En pre_save, l'exception annulait `user.save()` :
le compte restait inactif et non connecte, et `activate()` journalisait l'exception en erreur.
Le scan de carte QR et l'onboarding, qui activent aussi un compte, tombaient en erreur 500
dans le meme cas. Le signal pose maintenant le message sur l'utilisateur
(`message_reservation_annulee`), et `activate()` l'affiche apres la sauvegarde.
/ The pre_save signal raised to carry its message, which cancelled the save. It now sets an
attribute that `activate()` displays.

### 3 bis. Wizard evenement : tag de plus de 50 caracteres → erreur 500 (BILLETTERIE-COOP-TM)

**Quoi / What :** l'etape « evenement » du wizard refuse un tag de plus de 50 caracteres avec un
message de formulaire (« Un tag fait au plus 50 caractères. Séparez les tags par des virgules. »).
/ The event wizard step rejects a tag longer than 50 characters with a form error.

**Pourquoi / Why :** les tags sont decoupes sur `,` et `;`. Saisis a la facon des reseaux sociaux
(`#tag1 #tag2 #tag3`), ils formaient un seul tag trop long pour `Tag.name` (50) : `DataError` en
base a la finalisation, erreur 500.
/ Space-separated hashtags became one tag longer than `Tag.name` allows: DataError, 500.

### 3 ter. Adresse postale supprimee → activation d'un module en erreur 500 (BILLETTERIE-COOP-TJ)

**Quoi / What :** supprimer une adresse postale vide le cache de la `Configuration` du lieu.
/ Deleting a postal address clears the venue's `Configuration` cache.

**Pourquoi / Why :** `Configuration.postal_address` est en `SET_NULL`, applique par un `UPDATE`
SQL, sans `save()`. Le cache django-solo (memcached, 300 s) gardait l'ancien id. Pendant 5 minutes,
tout `get_solo().save()` (ex. activer un module depuis le tableau de bord) le reecrivait :
`IntegrityError` sur la cle etrangere. `clear_cache()` ne supprime qu'une cle, prefixee par le
schema du lieu (`django_tenants.cache.make_key`) : les autres lieux ne sont pas touches.
/ SET_NULL bypasses save(), so the solo cache kept a dangling id; the next save() rewrote it.
The cache key is per schema: other venues are untouched.

### 3 quater. Formulaire de connexion envoye vide : bruit Sentry (BILLETTERIE-COOP-FN)

**Quoi / What :** un email vide ou invalide dans les formulaires de connexion (`login_fullpage`,
`connexion`) est journalise en `warning`, plus en `error`. Le comportement ne change pas : le
formulaire est reaffiche avec l'erreur.
/ Invalid login email is logged as a warning instead of an error; behaviour unchanged.

**Pourquoi / Why :** 98 issues Sentry depuis 12/2025 pour une simple saisie invalide (surtout des
robots : le champ est deja `type="email" required`).
/ 98 Sentry events for plain invalid input, mostly bots.

### 3 quinquies. Reservation refusee « l'objet n'existe pas » (BILLETTERIE-COOP-EG + EF)

**Quoi / What :** `ReservationValidator.validate_options` journalise l'absence d'evenement en
`warning` (plus en `error`).
/ `validate_options` logs a missing event as a warning instead of an error.

**Pourquoi / Why :** en PreProd, le champ `event` filtrait sur `datetime__gte=now() - 1 jour`,
calcule une seule fois au demarrage de gunicorn : des evenements encore en vente etaient refuses
(« l'objet n'existe pas »), avec deux alertes Sentry par essai (EG dans la vue, EF dans
`validate_options`). Deja corrige sur cette branche (commit `d4096b08` : queryset sans date,
controle de vente a chaque requete dans `validate_event` ; vue `reservation` en `warning`).
Restait le `logger.error` de `validate_options`, atteint quand l'UUID envoye n'existe pas.
/ The date filter was computed once at startup; already fixed on this branch. Only the
`validate_options` error log remained.

### 3 sexies. Adhesion admin avec carte : erreur 500 et adhesions en double (BILLETTERIE-COOP-RE)

**Quoi / What :**
- Le numero de carte saisi est mis en majuscules avant la verification ET la liaison chez Fedow.
- La liaison (faite apres l'enregistrement, dans un `on_commit`) ne leve plus jamais d'exception
  (`lier_la_carte_a_l_adherent_chez_fedow`). Si Fedow refuse : carte deja sur le wallet de cet
  adherent (double envoi) → `warning` ; sinon → `logger.error` (alerte Sentry, adhesion sans carte).
- `fedow_api.linkwallet_card_number` journalise un refus en `warning` : c'est l'appelant
  (admin, caisse) qui decide de la gravite.
/ Card number uppercased before check and link; the post-commit link never raises; a real
refusal stays an error log, a double submit is only a warning.

**Pourquoi / Why :** la recherche Fedow accepte toute casse, la liaison compare la casse exacte :
une saisie `8a4f25bb` passait la verification puis echouait a la liaison. L'exception tombait
APRES l'enregistrement de l'adhesion : erreur 500, l'admin renvoyait le formulaire, et chaque
essai creait une adhesion de plus, sans carte.
/ Fedow lookup is case-insensitive, link is not; the post-commit crash made admins resubmit,
creating duplicate memberships.

**A verifier en production :** adhesions en double et cartes non liees sur `la-glissade`
(carte `8A4F25BB`) et `passreve` (`AF68A3D0`, `FA258121`, `243F4304`, `52B1A65D`, `027646DB`).

### 3 septies. Carte perdue : une seule fonction, les deux registres (BILLETTERIE-COOP-TW)

**Quoi / What :**
- Nouvelle fonction `declarer_la_carte_perdue(porteur, numero_carte, declarant)`
  (`BaseBillet/views.py`) : detache la carte chez Fedow, PUIS dans Lespass
  (`CarteService.declarer_perdue`), et journalise qui a declare. Appelee par les deux boutons
  « carte perdue » : `/my_account/` (l'usager) et la fiche usager de l'admin.
- Les droits restent dans chaque vue : l'usager (email valide, sa propre carte) d'un cote ;
  `TenantAdminPermission` (admin du lieu ou superuser) de l'autre, avec 403 sinon.
- `admin_lost_my_card` verifie l'identifiant de l'URL (400 si mal forme) et a ses propres
  messages (l'admin agit sur la carte de quelqu'un d'autre).
/ One shared function detaches the card on Fedow then in Lespass; rights stay in each view.

**Pourquoi / Why :**
- La vue admin ne rendait rien pour un superuser ou un non-admin (`None` → erreur 500 :
  l'incident Sentry), alors que l'admin s'ouvre aux superusers.
- Surtout, elle ne detachait la carte QUE chez Fedow. La caisse V2 lit d'abord
  `CarteCashless.user` : la carte perdue ouvrait encore le portefeuille de l'ancien porteur,
  et le porteur ne pouvait plus lier de nouvelle carte (`UserADejaCarte`). Oubli du commit
  `600831b0` (2026-09-06), qui n'avait branche que la vue usager.
/ The admin view returned None (500) and only detached on Fedow, leaving the lost card
spendable at the V2 POS.

**Complements (2026-10-11, apres relecture Fable + Opus) :**
- Fedow repond 404 quand la carte n'est pas, ou plus, a ce porteur (double clic, caisse V1,
  autre client Fedow). Exception dediee `CarteNonLieeAuPorteurChezFedow`
  (`fedow_connect/fedow_api.py`) : message INFO, simple warning, et la base Lespass est
  QUAND MEME alignee (detachement local filtre sur ce porteur). Le bouton repare donc une
  carte deja detachee chez Fedow. Une vraie panne Fedow (500, 403...) ne touche rien en local.
- Numero de carte mis en majuscules avant les deux appels.
- Carte primaire de caissier (`laboutik.CartePrimaire`) : retiree dans TOUS les lieux quand
  la carte est detachee en local (Fedow fait `primary_places.clear()` de son cote).
- Les 4 boutons « carte perdue » ont `hx-disabled-elt="this"` (anti double clic).
/ Fedow 404 now aligns Lespass instead of failing; cashier card removed in every venue;
anti double click on the buttons.

**Reste ouvert (hors de ce correctif) :** une carte detachee chez Fedow SANS passer par
Lespass (caisse V1 « VV » = vider + void, autre client Fedow) reste liee dans Lespass.
Le test `test_carte_perdue_cycle_complet.py[hors_lespass]` est ROUGE expres : il le prouve.
A traiter par une piste de fond (verification Fedow au scan en caisse V2, webhook Fedow,
ou reconciliation `CarteCashless.user` ↔ Fedow avant toute bascule V2).

### 3 octies. Apercu de skin : 3 vues partielles en erreur 500 (sans issue Sentry, branche seulement)

**Quoi / What :** nouvelle fonction `skin_preview_de_la_requete(request)` (`BaseBillet/views.py`)
qui lit et verifie `?skin_preview=` ; utilisee par `get_context` et par les 3 vues partielles
qui ne passent pas par lui : `MyAccount.my_cards`, `MyAccount.tokens_table`,
`EventMVT.partial_list` (filtres et « voir plus » de l'agenda).
/ Partial views now read the skin preview from the request.

**Pourquoi / Why :** le commit `a280e5c5` (apercu de skin dans l'admin) lisait
`context["skin_preview"]` dans ces 3 vues, dont le contexte ne contient pas cette cle :
`KeyError` → erreur 500 sur le tableau des soldes, le tableau des cartes et la liste de
l'agenda. Fait a la place de l'auteur, avec l'accord du mainteneur. Un revert etait exclu :
le commit `ff8c20ba` s'appuie dessus.
/ The skin preview commit read a missing context key in 3 partial views (500).

### 4. Pas de correctif de code : saturation PostgreSQL pendant la sauvegarde (BILLETTERIE-COOP-TQ, TK, TN, TS, RQ)

`SystemExit: 1` (worker gunicorn tue par son timeout) et `out of shared memory`, toujours vers
HH:02 : la sauvegarde horaire `pg_dumpall` (`cron/saveDb.sh`) saturait la table des verrous.
Deja corrige par `max_locks_per_transaction=4096` (`docker-compose.prod.yml`, commit `8c64e177`
du 2026-10-06, Postgres redemarre le 06/10 vers 04:37 UTC). Aucune recurrence depuis.
/ Already fixed by raising `max_locks_per_transaction`; no recurrence since 2026-10-06.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Event.full_url` : `max_length=500` |
| `BaseBillet/migrations/0229_alter_event_full_url.py` | Nouvelle migration (AlterField) |
| `Administration/templates/admin/asset/asset_change_form_before.html` | Bouton de remise masque si `total_value <= 0` |
| `Administration/admin_tenant.py` | Vue `bank_deposit` : message lisible + `warning` pour « Not enough token » ; `MembershipAddForm.clean_card_number` en majuscules ; nouvelle `lier_la_carte_a_l_adherent_chez_fedow` (on_commit sans exception) |
| `BaseBillet/views.py` (carte perdue) | `declarer_la_carte_perdue` ; `lost_my_card` et `admin_lost_my_card` l'appellent ; `admin_lost_my_card` en `TenantAdminPermission` + identifiant verifie |
| `tests/pytest/test_carte_perdue_cycle_complet.py` | Nouveau (Fedow reel) : cycle carte A creditee → perte → carte B, 3 facons de declarer ; superuser, non-admin (403), identifiant mal forme |
| `tests/pytest/test_vues_carte_branchees_sur_service.py` | Refus Fedow simule par une exception 500 (le client ne rend jamais False) + Fedow bien appele ; teardowns retires (piege 13.24) |
| `BaseBillet/views.py` (apercu de skin) | `skin_preview_de_la_requete` ; `my_cards`, `tokens_table`, `partial_list` l'appellent |
| `fedow_connect/fedow_api.py` (carte perdue) | `CarteNonLieeAuPorteurChezFedow` sur 404 de `lost_my_card_by_signature` ; refus journalises en warning |
| `Administration/templates/admin/membership/wallet_info.html`, `pages/templates/pages/{classic,V2}/vues/compte/partials/card_table.html`, `pages/templates/pages/V2/vues/compte/index.html` | `hx-disabled-elt="this"` sur les boutons « carte perdue » |
| `tests/pytest/test_skin_preview_partiels.py` | Nouveau : `partial_list` et `my_cards` repondent 200, avec ou sans apercu |
| `tests/e2e/test_carte_perdue_recharge_fed.py` | Nouveau : vraie recharge FED (Stripe), perte par double clic (Mon compte / admin), carte B, solde FED intact |
| `TECH_DOC/SKILLS/tibillet-test/SKILL.md`, `README.md`, `README.en.md`, `tests/README.md`, `tests/PIEGES.md` (9.40) | Installation de Playwright : chemin du venv demande a Poetry (`/DjangoFiles/.venv` n'existe pas) |
| `TECH_DOC/SESSIONS/TODO/CARTES-carte-perdue-en-post.md` + `INDEX.md` | Nouvelle fiche : passer les boutons « carte perdue » en POST |
| `tests/e2e/test_federation_asset_legacy_inter_lieux.py` | Apres remise en banque, la ligne a 0 est retrouvee par le nom du lieu (plus de bouton) |
| `fedow_connect/fedow_api.py` | `linkwallet_card_number` : refus journalise en `warning` (l'appelant decide) |
| `tests/pytest/test_membership_card_wallet_fedow.py` | 4 tests (Fedow reel) : saisie en minuscules, refus apres enregistrement, double envoi, carte d'un autre membre |
| `BaseBillet/signals.py` | `activator_free_reservation` : pose `message_reservation_annulee` au lieu de lever `ValueError` |
| `BaseBillet/signals.py` | Nouveau `vider_cache_configuration_apres_suppression_adresse` (`post_delete` sur `PostalAddress`) |
| `AuthBillet/views.py` | `activate()` : affiche `message_reservation_annulee` en avertissement apres `user.save()` |
| `BaseBillet/views.py` | `emailconfirmation()` : retrait du `except ValueError` devenu inutile ; `connexion` et `login_fullpage` : erreurs de saisie en `logger.warning` |
| `BaseBillet/validators.py` | `WizardEventSerializer.validate_tags` : 50 caracteres max par tag ; `ReservationValidator.validate_options` : `logger.warning` |
| `BaseBillet/templates/fonctionnel/event_wizard/_events_inner.html` | Champ tags en `is-invalid` en cas d'erreur |
| `tests/pytest/test_en_ligne_ecrit_la_vente.py` | `test_reservation_a_zero_annulee_garde_sa_vente_reglee` : le compte est active, le message est pose |

**i18n :** 7 nouvelles chaines FR (« Cette carte n'est pas, ou plus, liée à cette personne. », « Cette carte n'est plus liée à votre compte. », « Rien à remettre en banque », « Rien à remettre en banque pour ce lieu. », « Un tag fait au plus %(max)s caractères. Séparez les tags par des virgules. », « La carte a été détachée du portefeuille de cette personne. Elle peut maintenant en lier une nouvelle. », « Le détachement de la carte a échoué. Réessayez dans un instant. ») — workflow i18n a lancer.

---

## Comment tester (a la main) / Manual test

### Test 1 — evenement au nom long
1. Admin → Evenements → Ajouter.
2. Nom de 200 caracteres (le maximum du champ), une date, enregistrer.
3. Attendu : l'evenement est cree, pas d'erreur 500. Sa page publique s'ouvre via le lien.

### Test 2 — remise en banque, solde a zero
1. Admin → Assets Fedow → ouvrir un asset local dont un lieu a un solde a 0
   (par exemple juste apres une remise en banque).
2. Attendu : la ligne de ce lieu affiche « Rien à remettre en banque », sans bouton.
3. Les lignes avec un solde positif gardent le bouton « Valider le retour en banque ».

### Test 3 — remise en banque, solde positif (necessite un Fedow reel)
1. Cliquer « Valider le retour en banque » sur une ligne positive.
2. Attendu : toast « Remise en banque OK. », la ligne passe a 0 et le bouton disparait
   (le cache Fedow de la ventilation dure 30 s au plus).
3. Scenario automatise existant : `tests/e2e/test_parcours_fedow_reel.py`.

### Test 4 — reservation gratuite confirmee trop tard
1. Evenement gratuit, jauge 1. En navigation privee, reserver avec un email neuf (sans se connecter).
2. Ne pas cliquer le lien de confirmation. Pendant plus de 30 minutes, ou en reculant
   `Reservation.datetime` en base, faire prendre la derniere place par une autre personne.
3. Cliquer le lien de confirmation recu par mail.
4. Attendu : avertissement « Votre confirmation a pris plus de 30 minutes… », PUIS « Bienvenue » :
   le visiteur est connecte. En base : `is_active=True`, `email_valid=True`, reservation `C`.
5. Test automatise : `tests/pytest/test_en_ligne_ecrit_la_vente.py::test_reservation_a_zero_annulee_garde_sa_vente_reglee`.

### Test 5 — wizard evenement, tags en hashtags
1. Ouvrir le wizard de creation d'evenement (`/event/wizard/`), aller a l'etape « evenement ».
2. Champ tags : `#circuitscourts #producteurslocaux #artisansdart #lescles` (sans virgule).
3. Attendu : le formulaire revient avec le message « Un tag fait au plus 50 caractères… »,
   le champ tags en rouge, la saisie conservee. Pas d'erreur 500.
4. Avec `circuits courts, producteurs locaux` : l'evenement est ajoute normalement.

### Test 6 — supprimer l'adresse principale puis activer un module
1. Admin → Adresses postales : supprimer l'adresse liee a la configuration du lieu.
2. Tout de suite apres (moins de 5 minutes), tableau de bord → activer ou desactiver un module.
3. Attendu : le module bascule, pas d'erreur 500. En base : `Configuration.postal_address_id` est `NULL`.

### Test 7 — adhesion admin avec carte
1. Admin → Adhesions → Ajouter. Email neuf, un tarif, gratuit, numero d'une carte vierge
   saisi en MINUSCULES (ex. `ab12cd34`).
2. Attendu : retour a la liste (pas d'erreur 500), une seule adhesion creee, et la carte
   liee au membre (fiche du membre / « Mon compte » : la carte apparait).
3. Renvoyer le meme formulaire avec une carte deja liee a quelqu'un : le formulaire refuse
   (« This card is already linked to a user. »), aucune adhesion creee.
4. Tests automatises (Fedow de dev reel) :
   `tests/pytest/test_membership_card_wallet_fedow.py` (6 tests). Verifies par mutation :
   retirer la mise en majuscules, ou remettre l'appel direct dans le `on_commit`, les fait echouer.

### Test 8 — carte perdue, depuis l'admin et depuis Mon compte
1. Un usager avec une carte liee (parcours /qr). Admin → fiche de l'usager → « carte perdue ».
2. Attendu : message « La carte a été détachée du portefeuille de cette personne… », pas de 500.
   En base : `CarteCashless.user` de la carte est `NULL`.
3. L'usager lie une nouvelle carte par /qr : elle est acceptee, son solde y est.
4. Meme chose depuis /my_account/ (bouton de l'usager).
5. Connecte en superuser sans etre admin du lieu : le bouton fonctionne aussi.
6. Double clic sur le bouton : une seule requete part ; si un second passe quand meme,
   message INFO « Cette carte n'est pas, ou plus, liée à cette personne. », pas d'erreur.
7. Tests automatises (Fedow de dev reel) : `tests/pytest/test_carte_perdue_cycle_complet.py`
   (11 verts + `[autre_client_fedow]` en xfail strict) et l'E2E
   `tests/e2e/test_carte_perdue_recharge_fed.py` (vraie recharge FED). Verifies par mutation :
   sans detachement local, sans permission admin, detachement malgre un refus Fedow,
   identifiant non verifie, 404 traite comme un refus, carte primaire non retiree, et
   `hx-disabled-elt` retire (cote admin) → rouges.

### Verifs DB
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import Event
with tenant_context(Client.objects.get(schema_name='lespass')):
    with transaction.atomic():
        e = Event.objects.create(name='x'*200, datetime=timezone.now())
        print('OK', len(e.full_url))
        transaction.set_rollback(True)
"
```
Attendu : `OK 263` (ou proche selon le domaine), sans `DataError`.

### Sentry
- Commit : `Fixes BILLETTERIE-COOP-T7`, `Fixes BILLETTERIE-COOP-TR`, `Fixes BILLETTERIE-COOP-TP`, `Fixes BILLETTERIE-COOP-TM`, `Fixes BILLETTERIE-COOP-TJ`, `Fixes BILLETTERIE-COOP-FN`, `Fixes BILLETTERIE-COOP-EG`, `Fixes BILLETTERIE-COOP-EF`, `Fixes BILLETTERIE-COOP-RE`, `Fixes BILLETTERIE-COOP-TW`.
- BILLETTERIE-COOP-TQ, TK, TN, TS, RQ : deja corrigees par la config Postgres, a resoudre a la main.
- FEDOW-DJANGO-4Z (projet Fedow) : a resoudre a la main, aucun code Fedow modifie.
