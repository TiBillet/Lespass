# Anonymiser une copie de production

Script : `anonymiser_dump.py`. Spec : `TECH_DOC/SESSIONS/OBSERVATOIRE/CHANTIER-03-anonymisation-des-dumps.md`.

Ce n'est **pas** une commande Django : `manage.py` ne le voit pas. Il n'utilise que la
bibliothèque standard de Python (3.9 ou plus).

## Ce qu'il fait

- Il lit un dump PostgreSQL en texte (Lespass, LaBoutik V1) ou une base SQLite (Fedow),
  compressés en `.gz` ou non. Le format est reconnu par les premiers octets du fichier.
- Il écrit un **nouveau** fichier à côté. L'entrée n'est jamais modifiée.
- Il remplace les e-mails **partout**, ainsi que les clés API, mots de passe, clés RSA,
  noms, prénoms, pseudos, noms de connexion et téléphones d'une liste de colonnes.
- Il vide les sessions, les jetons et le journal de l'admin.
- Il relit sa sortie pour vérifier qu'il ne reste aucun vrai e-mail.
- Il affiche un rapport : des nombres et des noms de colonnes, **jamais une valeur**.

## La commande

Passer **toutes les bases dans la même commande** : le faux e-mail d'une personne est
alors le même dans les trois. Fedow retrouve un utilisateur Lespass par son e-mail ; deux
lancements séparés donnent deux faux e-mails différents.

```bash
python3 seo/scripts_observatoire/anonymiser_dump.py \
    /chemin/lespass.sql.gz \
    /chemin/fedow.sqlite3 \
    /chemin/laboutik.sql.gz
```

Sorties : `lespass.anonyme.sql.gz`, `fedow.anonyme.sqlite3`, `laboutik.anonyme.sql.gz`,
dans le dossier de chaque entrée, lisibles par leur seul propriétaire (`600`). Une sortie
déjà présente n'est jamais écrasée.

| Code de sortie | Sens |
|---|---|
| 0 | Tout est anonymisé, contrôle OK. |
| 1 | Sortie écrite, mais le contrôle final a trouvé de vrais e-mails (tables nommées dans le rapport). |
| 2 | Entrée refusée, rien n'est gardé pour ce fichier. |
| 3 | Erreur pendant le traitement : seul le type de l'erreur est affiché (son message pourrait contenir une donnée de prod). |

Si le script est arrêté en cours de route (`kill`, terminal fermé, `docker stop`), il
supprime son fichier de travail, `<sortie>.travail-PAS-ENCORE-ANONYME`. Après un
`kill -9`, ce fichier peut rester : c'est encore une copie de la prod, le supprimer.

## Les entrées

- **Lespass, LaBoutik V1** : le `*.sql.gz` du cron (`pg_dumpall | gzip`), ou un
  `pg_dump` en texte. Un dump au format custom (`pg_dump -Fc`) est refusé : le convertir
  d'abord avec `pg_restore -f - fichier.dump | gzip > fichier.sql.gz`.
  Un dump fait avec `--inserts` est refusé aussi.
- **Fedow** : `backup/snapshot/db.sqlite3` (le dernier snapshot vérifié), ou une archive
  borg extraite. Jamais la base vivante de Fedow : une copie au repos.

## Charger la copie anonymisée

Dans un Postgres **jetable**, ou dans la pile à part
(`TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-copie-prod.md`). Toujours avec
`ON_ERROR_STOP` : sans lui, `psql` continue après une erreur, et une table peut arriver
vide sans que rien ne le signale.

```bash
docker run -d --rm --name copie_anonyme --network none -e POSTGRES_PASSWORD=jetable postgres:13-bookworm
zcat lespass.anonyme.sql.gz | docker exec -i copie_anonyme psql -q -v ON_ERROR_STOP=1 -U postgres -d postgres
```

## Se connecter sur la copie

Personne ne peut se connecter avec un mot de passe, et tous les e-mails sont faux. Pour
utiliser l'admin, remettre son propre e-mail sur son compte (copie Lespass, dans le
conteneur Django branché sur la copie) :

```bash
python manage.py shell -c "from AuthBillet.models import TibilletUser; \
u = TibilletUser.objects.get(pk='<uuid de ton compte>'); u.email = u.username = 'moi@exemple.fr'; u.save()"
```

Puis se connecter par code (OTP) : le mail part vers Mailpit.

## Ce qui reste en clair

- dates de naissance, codes postaux ;
- noms et téléphones écrits dans du texte libre ou du JSON (réponses aux formulaires,
  commentaires) : seuls les e-mails y sont remplacés ;
- adresses IP et user agents ;
- identifiants Stripe (`cus_…`, `acct_…`, `pi_…`) et identifiants de cartes NFC ;
- e-mails cachés dans du base64 ou des données signées ;
- Fedow : les e-mails de `fedow_core_transaction.comment` et `.metadata`. Ces colonnes
  entrent dans le hash chaîné des transactions ; le rapport les compte.

Le résultat est **pseudonymisé**, pas anonyme au sens du RGPD : on peut encore retrouver
une personne par recoupement. La copie reste une donnée personnelle, à garder sur une
machine protégée et à supprimer après usage.

## Ce qui ne marche plus sur la copie

C'est attendu :

- les appels à Stripe, Ghost, Brevo, Formbricks, Sunmi, Odoo, Dokos, Fedow et LaBoutik V1
  (clés vides) ;
- les QR codes des billets, les signatures des wallets, la poignée de main LaBoutik ↔
  Fedow (clés RSA vides) ;
- la vérification d'intégrité des anciennes lignes de caisse (clé HMAC vide).

## Quand un modèle gagne un champ secret

Le rapport nomme les **colonnes suspectes non traitées** : un nom qui contient `key`,
`secret`, `token`, `password`, `pem`, `pin`, `api` ou `otp`, sans règle. Le script n'y
touche pas. Ajouter la colonne dans `REGLES_POSTGRES` ou `REGLES_SQLITE` si c'est un
secret, sinon dans `COLONNES_VUES_ET_LAISSEES`.
