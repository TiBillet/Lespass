# Récap quotidien des admins — Plan d'implémentation

> **Pour les agents :** SOUS-SKILL REQUIS — `superpowers:subagent-driven-development` (recommandé)
> ou `superpowers:executing-plans`. Les étapes sont en cases à cocher (`- [ ]`).
>
> **Hub :** [INDEX.md](INDEX.md) · **Spec :** [SPEC.md](SPEC.md) — à lire en entier avant la
> tâche 1. Le plan ne répète pas les raisons : elles sont dans la spec.

**But :** chaque matin, un mail par lieu aux admins (et à `rapport_emails` en périodicité J) qui
résume tout ce qui s'est passé la veille, avec les tickets Z en pièce jointe. Aucun mail sans
contenu. Le mail séparé du Z journalier disparaît.

**Décisions du mainteneur sur le plan (2026-10-18) :** montant d'un remboursement = l'argent
rendu (`-total_ttc`) ; exécution **un agent par tâche, relu avant la suivante** ; tâche 8 ajoutée
(démo du flush).

**Architecture :** un module `Administration/recap_quotidien.py` calcule et envoie le récap d'un
lieu. Il est appelé **à la fin** de `generer_les_clotures_automatiques_du_lieu`
(`comptabilite/tasks.py`), après le filet J et les H/M/A, dans la même sous-tâche horaire : pas
de nouvelle tâche Celery beat. Six champs de date nouveaux rendent « créé hier » et « annulé
hier » fiables.

**Stack :** Django 4.2 · django-tenants · django-solo · Celery · pytest (`FastTenantTestCase`).
Aucune nouvelle dépendance.

---

## Contraintes globales

1. **AUCUNE opération git d'écriture.** Ni `add`, `commit`, `push`, `merge`, `rebase`,
   `checkout --`, `restore`, `stash`, `reset --hard`, `clean -f`, `branch -D`. Les étapes
   « Commit » demandent **d'afficher le message suggéré** (sans aucune mention de Claude) dans le
   rapport, puis de **s'arrêter**.
2. **Toute commande Python passe par le conteneur** (`.venv` partagé par bind-mount : `poetry`,
   `pytest` ou `ruff` lancés depuis l'hôte le détruisent). Tests : `make test ARGS="tests/pytest/<fichier>.py"`
   ou `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/<fichier>.py -v`.
3. **`ruff format` seulement sur un fichier NEUF.** Sur un fichier pré-existant : jamais. `ruff
   check --fix` sur un pré-existant seulement après inspection à la main des imports « inutiles »
   (`admin*.py` surtout), puis `manage.py check`.
4. **Ne jamais lancer `makemessages` ni `compilemessages`.** msgid des `_()` en **français**.
   Signaler en fin de tâche le nombre de chaînes ajoutées.
5. **Ne pas lancer de serveur.** Le serveur de dev est tenu par le mainteneur (byobu).
6. **D'autres agents travaillent sur la même base** : lancer les fichiers de test ciblés ; la
   suite complète seulement avec l'accord du mainteneur. Les migrations se **génèrent** avec
   `makemigrations` ; leur application sur la base de dev se fait **avec l'accord du mainteneur**.
7. **FALC** (skill `djc`) : noms verbeux, commentaires FR (FALC) + une ligne EN, boucles `for`
   simples, `LOCALISATION` en tête de docstring. Le commentaire décrit le code tel qu'il est,
   jamais l'historique de la session.
8. **Laisser planter** : pas de `try/except` qui étouffe une erreur de calcul. Une erreur remonte
   à la sous-tâche du lieu (Sentry).
9. **Chaque test est vu ÉCHOUER** sur une mutation volontaire du code avant d'être livré (noter
   la mutation dans le rapport). Zéro `pytest.skip`.
10. **Toutes les heures par `timezone.now()`** (jamais `datetime.now()` ni `date.today()`). Les
    tests patchent `django.utils.timezone.now`.
11. **Les champs `auto_now_add` ne se fixent pas à la création** : dans les tests, créer l'objet
    puis `Modele.objects.filter(pk=…).update(champ=moment)`.
12. Avant d'écrire un test, relire dans `tests/PIEGES.md` : 9.1 (`tenant_context`, jamais
    `schema_context`), 13.4 (intercepter les `.delay()`), 13.5 (le cache django-solo survit au
    rollback ; le piège recommande de patcher `get_solo()`. Ici on suit le motif de
    `test_cloture_unique.py` : **chaque `setUp` écrit toutes les valeurs lues par le récap puis
    fait `configuration.save()`**, pour que le cache porte les valeurs du test), 9.63, 9.86,
    P.ONBOARD.5.
13. Heures des tests : **jamais une égalité d'heure** avec un seuil (convention des tests de
    clôture) : 7h10, 8h10, 4h10…

## Points de vigilance (non couverts par la spec, à tester)

1. **Nuit de changement d'heure** : la veille dure 23 h ou 25 h. La fenêtre se calcule en heure
   locale (minuit → minuit) puis se convertit en UTC → test dans la tâche 3.
2. **Objets sans personne** : une `Membership` peut avoir `user=None` (accepté par design), une
   `Contribution` peut avoir `contributor=None`. Une ligne du récap ne plante jamais sur un `None`
   → tests dans les tâches 3 et 4.
3. **Plus de 10 lignes** dans une rubrique : 10 montrées, puis « et N autres » → test tâche 3.
4. **Aucun destinataire** (aucun admin, `config.email` vide) : pas de mail, un `logger.warning`,
   le marqueur est posé quand même → test tâche 6.
5. **Les tests horaires existants** (`test_cloture_unique.py`, `test_reprise_clotures.py`,
   `test_comptabilite_celery.py`) passent désormais par le récap : ils ne doivent ni casser ni
   envoyer de mail réel → tâche 7, étape de vérification.

---

## Fichier de test

Un seul fichier neuf : **`tests/pytest/test_recap_quotidien.py`**, une classe par tâche, toutes en
`FastTenantTestCase` sur le schéma **`test_recap_quotidien`** (domaine
`test-recap-quotidien.tibillet.localhost`, `setup_tenant` pose `tenant.name = "Test recap
quotidien"`). Motif à copier : l'en-tête et le `setUp` de `tests/pytest/test_cloture_unique.py`
(`connection.set_tenant`, `LaboutikConfiguration.get_solo().save()`, `Configuration` réécrite :
`fuseau_horaire="Europe/Paris"`, `heure_de_fermeture=time(2, 0)`, `language="fr"`,
`rapport_emails=""`, `rapport_periodicite=Configuration.PERIODICITE_NONE`, `email="lieu@example.org"`).

Fabriques existantes à utiliser plutôt que de réécrire : `tests/pytest/fabriques_vente.py`
(`creer_tarif_vendu`, `fabriquer_vente_encaissee`), `fabriques_panier.py` (`creer_utilisateur`,
`creer_adhesion`, `creer_ressource_avec_tarif`, `creer_evenement_avec_tarif`),
`fabriques_reservation.py` (`creer_evenement_et_produit`). Pour les bénévoles :
`tests/pytest/test_benevolat_equipe.py` ; pour les initiatives : `tests/pytest/test_en_ligne_ecrit_la_vente.py`.

Dates de référence des tests : **le mardi 13 octobre 2026**, heure de Paris (CEST, UTC+2).
« La veille » = lundi 12 octobre. Pour la nuit de changement d'heure : **dimanche 25 octobre
2026** (passage à CET), récap du lundi 26.

---


## RÈGLE DE SÉCURITÉ MÉMOIRE (ajoutée après incident)
Un test a déjà consommé 28 Go et fait fermer la session du mainteneur. TOUT lancement de pytest se fait ainsi, sans exception :
`docker exec lespass_django bash -c "ulimit -v 8000000; timeout 600 poetry run pytest /DjangoFiles/tests/pytest/<fichier>.py -v"`
Un `MemoryError` ou un délai dépassé = un test fautif : arrête-toi, ne relance pas en boucle, signale-le. Jamais de `MagicMock` passé là où le code le rend dans un gabarit ou une réponse JSON.
