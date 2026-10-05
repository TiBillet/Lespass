# Issue #319 : remboursements et avoirs perdus vers LaBoutik / Refunds and credit notes lost on their way to LaBoutik

**Date :** 2026-10-01
**Migration :** Non

**FR :** Quand on rembourse un billet ou une adhésion, ou quand on émet un avoir, Lespass
envoie une ligne négative à LaBoutik (`/api/refundfromlespass`). LaBoutik rattache cette
ligne à la vente d'origine. Deux cas faisaient échouer l'envoi, sans relance et sans
alerte lisible :

1. **La vente d'origine n'avait jamais été envoyée à LaBoutik** (serveur indisponible au
   moment de la vente, par exemple). LaBoutik répondait 404. L'ancien log disait
   « Serveur down ? », puis « endpoint introuvable » : les deux étaient trompeurs.
   Maintenant, `send_refund_to_laboutik` vérifie d'abord la vente d'origine. Si elle n'est
   pas encore dans LaBoutik et qu'elle est payée, la tâche relance `send_sale_to_laboutik`,
   puis réessaie le remboursement plus tard (au moins 30 s, 20 tentatives au maximum).
   Si la vente d'origine n'est pas payée, ou si on ne la retrouve pas, la tâche abandonne
   avec un log qui donne la raison.
2. **Deux avoirs n'envoyaient pas l'uuid de la vente d'origine** : l'annulation d'adhésion
   avec avoirs et l'action admin « Avoir » sur une ligne de vente. LaBoutik répondait 400.
   Ces deux avoirs remplissent maintenant `metadata['original_lignearticle_uuid']`. Les
   anciens avoirs sans cette clé sont rattrapés : la tâche l'ajoute dans ce qu'elle envoie,
   à partir de `credit_note_for`.

Les logs sont aussi plus précis :
- serveur LaBoutik injoignable : nom de la tâche, URL du serveur, tenant, numéro de
  tentative et exception (dans les 3 tâches d'envoi vers LaBoutik) ;
- 404 sur un remboursement : uuid de la vente d'origine inconnue ;
- autre erreur 4xx : début de la réponse de LaBoutik.

Ce qui ne change pas : les ventes, remboursements et avoirs déjà abandonnés ne sont pas
renvoyés automatiquement.

**EN :** Refunds and credit notes sent to LaBoutik were lost in two cases. (1) The original
sale had never reached LaBoutik, which answered 404. The refund task now re-sends the
original sale and retries the refund later. (2) Two credit note flows (membership
cancellation, admin "Credit note" action) did not send `original_lignearticle_uuid`, so
LaBoutik answered 400. They now do, and the task adds it for older credit notes. LaBoutik
logs now name the task, server, tenant, attempt and error. Lines already given up are not
re-sent.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/tasks.py` | Nouveau helper `trouver_ligne_de_vente_originale`. `send_refund_to_laboutik` : vérifie la vente d'origine, relance son envoi et se replanifie, complète `original_lignearticle_uuid` dans le payload, logs 404/4xx précis. Logs « serveur injoignable » détaillés dans les 3 tâches LaBoutik |
| `BaseBillet/views.py` | Annulation d'adhésion avec avoirs : l'avoir porte `original_lignearticle_uuid` |
| `Administration/admin_tenant.py` | Action « Avoir » (`emettre_avoir`) : l'avoir porte `original_lignearticle_uuid` |
| `tests/pytest/test_send_refund_to_laboutik.py` | Nouveaux tests : vente pas encore envoyée, vente envoyée, réponse 404, ligne sans vente d'origine, recherche par metadata |
| `tests/pytest/test_admin_annulation_abonnement_stripe.py` | Nouveau test : l'avoir d'annulation porte l'uuid de la vente d'origine |
