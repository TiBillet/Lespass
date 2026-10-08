# Reprise des ventes : clôture « reprise », rattrapage plafonné, FEC, admin (chantier 05, fiche R, session R-3) / Sales takeover: "reprise" closure, capped catch-up, FEC, admin (worksite 05, sheet R, session R-3)

**Date :** 2026-10-08
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Nouvelle commande `manage.py creer_la_cloture_de_reprise [--schema …]`. Elle crée, pour
  chaque lieu, une J « reprise » qui couvre tout l'historique des ventes : de la première
  vente réglée jusqu'à l'heure de la commande. La commande est synchrone et n'envoie
  aucun mail. La J porte le total perpétuel de tout l'historique et `"reprise": true`
  dans l'en-tête de son rapport, posé avant l'empreinte.
  - Lieu qui a déjà sa J reprise : rien n'est fait.
  - Lieu qui a déjà une J ordinaire : la J reprise est refusée, un message le dit, et la
    commande passe au lieu suivant.
  - Lieu sans vente réglée : aucune J.
- La **mise en service** de la comptabilité d'un lieu est la fin de sa J reprise. Une
  seule fonction la lit : `mise_en_service_du_lieu()` (`comptabilite/tasks.py`).
- Rattrapage H / M / A de la tâche horaire : au plus **12 clôtures au total** par lieu et
  par passage.
- Aucun mail pour une clôture dont la fin est avant ou égale à la mise en service.
- FEC refusé pour la J reprise et pour toute H / M / A qui commence avant la mise en
  service. Message : « Le FEC commence à la date de mise en service de la comptabilité
  (jj/mm/aaaa). Pour avant, utilisez les rapports mensuels. » La date est en heure du
  lieu. La balance n'est pas touchée (QO-2).
- Admin des ventes : un règlement de référence « reprise » n'a plus de lien Stripe ;
  l'écran affiche « reprise ».

/ New synchronous command creating one "reprise" J per venue (whole history, marked
before sealing, no mail; replay-safe; refused when an ordinary J exists). Its end is the
accounting go-live. The hourly catch-up creates at most 12 H / M / A per run. No mail
for a closure ending at or before the go-live. The FEC is refused for the "reprise" J and
for any H / M / A starting before the go-live; the trial balance is unchanged. No Stripe
link for a "reprise" payment in the admin.

**Pourquoi / Why :** R-1 et R-2 donnent à chaque ancienne ligne sa vente. Il manquait
les clôtures :
- sans J reprise, le premier filet ferait une J de plusieurs années ;
- sans plafond, le rattrapage créerait des centaines de clôtures et de mails d'un coup ;
- un FEC fait d'une J de plusieurs années serait faux.

Références : fiche `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md` §11,
§12 (étapes 10 et 11), §13 R-3, §17 (QO-2, QO-4) ; brief `CHANTIER-05-briefs/05-R-3.md` ;
décisions de l'orchestrateur du 2026-10-08 (SUIVI §4).
/ Without these, the first net J would span years, the catch-up would create hundreds
of closures and mails at once, and a multi-year FEC would be wrong.

Information (fiche R §11.2) : les H / M / A de l'historique portent le perpétuel de la
dernière J (la J reprise, ou une J suivante). Leurs numéros se mêlent à ceux des
nouvelles J : la chaîne reste valide, mais les numéros ne suivent pas l'ordre du temps.
Le rattrapage crée d'abord les semaines, puis les mois, puis les années. Pour un lieu
qui a des années d'historique, les mois et les années n'arrivent donc qu'après toutes
ses semaines (12 par heure).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/tasks.py` | Paramètre `reprise` de `_creer_la_cloture_journaliere` et de `_enregistrer_la_cloture` (marque avant l'empreinte) ; `est_la_j_de_reprise`, `la_j_de_reprise_du_lieu`, `mise_en_service_du_lieu` ; garde des mails dans `demander_l_email_automatique_si_configure` ; plafond `PLAFOND_DES_CLOTURES_CALENDAIRES_PAR_PASSAGE` dans `generer_les_clotures_automatiques_du_lieu` |
| `comptabilite/admin.py` | `exporter_fec` : refus avant la mise en service (le refus est ici, pas dans `fec.py`) |
| `Administration/admin_tenant.py` | `_adresse_stripe_d_un_reglement` : aucun lien pour la référence « reprise » |
| `comptabilite/management/commands/creer_la_cloture_de_reprise.py` | Nouveau : la commande de la J reprise |
| `tests/pytest/test_reprise_clotures.py` | Nouveau : 13 tests (schéma dédié `FastTenantTestCase`) |

### Chaînes i18n ajoutées / Added i18n strings
Une seule chaîne, dans `comptabilite/admin.py` : « Le FEC commence à la date de mise en
service de la comptabilité (%(date)s). Pour avant, utilisez les rapports mensuels. » Le
workflow i18n est à lancer par le mainteneur. Les messages de la commande sont en
français, sans `_()`, comme ceux de `reprendre_les_ventes_existantes`.

### Tests
- Rouge (étape 1, code absent) : `12 failed`.
  - 11 échecs : `CommandError: Unknown command: 'creer_la_cloture_de_reprise'`.
  - 1 échec : `AssertionError` sur le lien Stripe d'un règlement « reprise ».
- Vert (étape 2) : `13 passed`. Le 13ᵉ test a été ajouté après la décision de
  l'orchestrateur : `test_j_reprise_refusee_si_le_lieu_a_deja_une_j_ordinaire`.
- Sans modification, tous verts :
  - caractérisation, clôtures et reprise des ventes : `131 passed`
    (`test_caracterisation_*`, `test_cloture_*`, `test_reprise_des_ventes.py`) ;
  - comptabilité et FEC : `119 passed` (`test_comptabilite_*`, `test_fec_equilibre.py`) ;
  - admin des ventes : `186 passed` (`test_admin_alignements_et_fiche_vente.py`,
    `test_admin_vente.py`, `test_admin_avoir_sur_un_article.py`,
    `test_rapport_unique.py`).

### Mutations / Mutations
Chaque mutation a été jouée par l'ouvrier, puis le code a été remis tel quel (empreinte
md5 vérifiée). Chacune fait échouer le test attendu, et lui seul.

| Mutation | Fichier:ligne | Test en échec |
|---|---|---|
| Marque posée après le scellement | `comptabilite/tasks.py:382-383` déplacées juste avant `cloture.save()` (l.406) | `test_j_reprise_marquee_dans_l_en_tete_et_empreinte_valide` |
| Plafond retiré | `comptabilite/tasks.py:942` (`nombre_de_clotures_calendaires_creees += 1` → `pass`) | `test_rattrapage_plafonne_a_douze_par_passage` |
| Garde mail retirée | `comptabilite/tasks.py:714-715` (`return` → `pass`) | `test_aucun_mail_pour_une_cloture_finie_avant_la_mise_en_service` |
| Mail : `<=` → `<` | `comptabilite/tasks.py:712` | `test_aucun_mail_pour_une_cloture_finie_avant_la_mise_en_service` (février finit à la mise en service) |
| FEC : `<` → `<=` | `comptabilite/admin.py:273` | `test_fec_accepte_apres_la_mise_en_service` |
| FEC accepté sur la J reprise | `comptabilite/admin.py:275` (retirer `est_la_j_de_reprise(cloture) or`) | `test_fec_refuse_sur_la_j_reprise_avec_le_message` |
| Lien Stripe rendu pour « reprise » | `Administration/admin_tenant.py:2404-2405` (retirées) | `test_reglement_reprise_sans_lien_stripe_dans_l_admin` |
| Rejeu présenté comme un refus | `comptabilite/management/commands/creer_la_cloture_de_reprise.py:114` (`if False:`) | `test_j_reprise_rejouee_ne_cree_pas_une_seconde_cloture` |
| J reprise créée deux fois | `creer_la_cloture_de_reprise.py:114` et `:125` (`if False:` les deux) | `test_j_reprise_rejouee_ne_cree_pas_une_seconde_cloture`, `test_j_reprise_refusee_si_le_lieu_a_deja_une_j_ordinaire` |
| Refus « J ordinaire » retiré | `creer_la_cloture_de_reprise.py:125` (`if False:`) | `test_j_reprise_refusee_si_le_lieu_a_deja_une_j_ordinaire` |

---

## Comment tester (a la main) / Manual test

### Test 1 — la J reprise d'un lieu
1. Sur un lieu de dev qui a des ventes réglées et **aucune** clôture J :
   `docker exec lespass_django poetry run python /DjangoFiles/manage.py creer_la_cloture_de_reprise --schema <schéma>`
2. Attendu : « Lieu <schéma> : J reprise n° N créée, du … au … (X ventes, total Y
   centimes). »
3. Dans l'admin, « Clôtures » : une J dont la période part de la première vente du lieu.
4. Relancer la commande. Attendu : « J reprise déjà faite (clôture n° N), rien à faire. »
5. Mailpit : aucun mail.

### Test 2 — lieu qui a déjà une J ordinaire
1. Lancer la commande sur un lieu qui a déjà des clôtures J (base de dev ordinaire).
2. Attendu, en rouge : « J reprise refusée : le lieu a déjà une clôture journalière
   ordinaire (n° …) ». Aucune clôture créée ; les autres lieux sont traités.

### Test 3 — FEC refusé avant la mise en service
1. Ouvrir la J reprise du test 1 dans l'admin, cliquer « FEC ».
2. Attendu : aucun fichier ; message rouge « Le FEC commence à la date de mise en service
   de la comptabilité (jj/mm/aaaa). Pour avant, utilisez les rapports mensuels. » La date
   est celle de la commande, en heure du lieu.
3. PDF, CSV et Excel de la même clôture : toujours téléchargés.
4. Plan comptable, onglet « Gérer », balance d'une période qui contient la J reprise :
   affichée normalement.

### Test 4 — règlement « reprise » dans l'admin des ventes
1. Après `reprendre_les_ventes_existantes --executer` (R-2) sur un lieu qui a d'anciens
   remboursements Stripe : ouvrir un avoir repris.
2. Attendu : la colonne « Référence » des règlements affiche « reprise », sans lien.

### Verifs DB
```python
# docker exec lespass_django poetry run python /DjangoFiles/manage.py shell
from django_tenants.utils import tenant_context
from Customers.models import Client
from comptabilite.tasks import mise_en_service_du_lieu
with tenant_context(Client.objects.get(schema_name="<schéma>")):
    print(mise_en_service_du_lieu())
```
