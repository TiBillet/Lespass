# Supprimer les lieux jamais utilisés avant la bascule / Delete never-used venues before the switch-over

**Date :** 2026-10-07
**Migration :** Non

## Resume / Summary
**Quoi / What :** nouvelle commande `manage.py supprimer_lieux_inactifs`. À blanc par défaut,
elle liste les lieux sans aucune activité (8 critères, fiche 05-R §18) et ceux qu'elle garde,
avec leurs raisons. Avec `--executer --liste <domaines validés>`, elle supprime chaque lieu de
la liste encore inactif, dans sa propre transaction : schéma, domaines, ligne `Client`, fiche
d'onboarding, invitations et cache SEO. Les utilisateurs et les portefeuilles sont gardés. Puis
elle envoie un mail à chaque administrateur, qui liste ses lieux supprimés.
/ New command: dry run by default; with `--executer --liste`, deletes each listed venue that is
still inactive, one transaction per venue, keeping users and wallets, then mails each admin.

**Pourquoi / Why :** la nuit de la bascule, juste avant `migrate_schemas` (fiche §12 étape 2 bis) :
place en base et environ une heure de migration en moins (153 lieux sans trace sur la copie du
2026-10-06).
/ Space and about one hour of migration saved on the switch-over night.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/management/commands/supprimer_lieux_inactifs.py` | Nouvelle commande : options, suppression lieu par lieu, mails, rapports |
| `Administration/nettoyage_des_lieux.py` | Nouveau : détection (8 critères, références lues dans le catalogue), en SQL brut |
| `tests/pytest/test_supprimer_lieux_inactifs.py` | Nouveau : 20 tests (44 cas), lieux jetables `test_nettoyage_*` |

### Newsletter et formulaires branchés / Plugged-in newsletter and forms
Un lieu qui a branché un service est gardé, avec la raison « configuration personnalisée :
Ghost | Brevo | Formbricks » (critère 6). Le service compte comme branché quand l'une de ces
colonnes est remplie :
- `ghostconfig.ghost_key` ou `ghostconfig.ghost_url` ;
- `brevoconfig.api_key` ;
- `formbricksconfig.api_key`.

`formbricksconfig.api_host` ne compte pas : il a une valeur par défaut, remplie dans 303
lieux de production qui n'ont pas de clé. Vide veut dire NULL ou texte vide.
/ A venue with a newsletter or form service key is kept.

### Page d'accueil par défaut / Default home page
Sur une base déjà migrée, la migration `BaseBillet 0225` a créé dans chaque lieu une page
d'accueil (1 ligne `pages_page`, au plus 3 lignes `pages_bloc`). Le critère 5 la tolère, et
rien de plus. Une 2ᵉ page, un 4ᵉ bloc, un bloc hors de l'accueil ou une image
(`pages_imagegalerie`) gardent le lieu (« table non vide : pages_… »).
/ The default home page created by BaseBillet 0225 is tolerated, nothing more.

### Le mail / The mail
Il utilise le gabarit générique `emails/email_generique.html` (« Bonjour <adresse>, »,
« Bien à vous, »), que le mainteneur a accepté tel quel. Le texte est celui de la fiche §18
(version du 2026-10-07). Avec plusieurs lieux, il est mis au pluriel.

### Chaînes à traduire / Strings to translate
8 nouvelles chaînes (msgid en français), toutes dans le mail
(`Administration/management/commands/supprimer_lieux_inactifs.py`,
`construire_le_mail_d_un_administrateur`) :
1. « Votre espace TiBillet a été fermé »
2. « Votre espace TiBillet %(domaine)s, ouvert le %(date)s, n'a jamais été utilisé : aucun
   événement, aucune adhésion, aucune vente. Dans un souci de mutualisation, nous supprimons
   les espaces non utilisés : nous l'avons fermé et nous avons supprimé ses données. »
3. « %(domaine)s (ouvert le %(date)s) »
4. « Vos espaces TiBillet %(espaces)s n'ont jamais été utilisés : … nous les avons fermés et
   nous avons supprimé leurs données. »
5. « Si vous souhaitez en ouvrir un nouveau, n'hésitez pas à retourner sur
   https://tibillet.coop. Une nouvelle version de TiBillet arrive très bientôt. »
6. « Vos données personnelles : votre compte TiBillet (votre adresse email) reste ouvert, … »
7. « Bien à vous »
8. « L'équipe de la coopérative TiBillet »
Le workflow i18n est à lancer par le mainteneur.
La sortie à l'écran et les CSV restent en français, sans traduction : c'est un outil
d'exploitation, et les tests en lisent les valeurs.

---

## Comment tester (a la main) / Manual test

**Les tests passent par des lieux jetables. Ne jamais lancer `--executer` sur la base de
dev ni sur un lieu de démo.**

### Test 1 — tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_supprimer_lieux_inactifs.py -q
```
Attendu : 44 passed (environ 4 min 30, une cinquantaine de schémas copiés puis supprimés).

### Test 2 — passage à blanc sur une copie de production (orchestrateur)
```bash
manage.py supprimer_lieux_inactifs --rapport rapport.csv
```
1. Lire la liste « gardés ». Une raison `table non vide : <table>` montre une table qu'un
   lieu jamais utilisé peut quand même remplir. Elle est peut-être à ajouter à
   `TABLES_REMPLIES_SEULES` (`Administration/nettoyage_des_lieux.py`).
2. Lire aussi les raisons `configuration personnalisée : <colonne>` sur des lieux sans activité.
3. Vérifier qu'aucun nom de schéma n'apparaît, seulement des domaines.

### Test 3 — exécution sur la copie
```bash
manage.py supprimer_lieux_inactifs --liste domaines_valides.txt --executer --sans-mail \
    --rapport rapport.csv --traces-externes traces.csv
```
Contrôles après :
- aucun schéma sans `Client`, ni l'inverse ;
- nombre d'utilisateurs inchangé ;
- lieux restants inchangés ;
- noter la durée (dernière ligne du résumé).

### Verifs DB
- Aucun reste des tests :
  `select count(*) from pg_namespace where nspname like 'test\_nettoyage\_%'` → 0.
  Même chose sur `Customers_client.schema_name`.
