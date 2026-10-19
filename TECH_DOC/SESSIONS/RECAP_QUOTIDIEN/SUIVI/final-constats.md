# Relecture finale — constats à corriger (UNE passe)

## CHANGELOG/2026-10-18-recap-quotidien-admins.md
1. En-tête « Migration » : ajouter l'ORDRE de déploiement — migrer (`migrate_schemas`, exécuteur standard) AVANT de recharger le code (colonnes neuves sur Reservation, Membership, Event, Booking, Configuration : sinon chaque save()/create() plante), puis `supervisorctl restart gunicorn daphne celery` (sans redémarrer Celery, l'ancien code tourne : ancien mail du Z, pas de récap).
2. Dire clairement ce que reçoit désormais `rapport_emails` en périodicité « Journalier » : tout le récap (noms, e-mails des adhérents, réservations, annulations, bénévoles), tous les destinataires en `To:` — décision du mainteneur ; prévenir les lieux concernés si utile.
3. Démo (vers l.98) : « un flush après 7 h avec Celery beat actif déclenche aussi, le jour même, un récap de la veille (sans le Z) : la démo ne pose pas le marqueur ».
4. Test 4 (démo) : le flush envoie un vrai mail à la fin ; sans `EMAIL_HOST`/`EMAIL_PORT` dans le `.env` de dev, la FIN du flush plante (les données sont déjà écrites).
5. Ajouter une vérification avant déploiement : aucun lieu sans domaine primaire (`Client` sans `Domain(is_primary=True)`, hors public et WAITING_CONFIG) — sinon le récap de ce lieu plante chaque heure.

## comptabilite/tasks.py (generer_les_clotures_automatiques_du_lieu, vers l.1067-1100)
6. Entourer l'APPEL du récap d'un try/except dédié : `logger.exception(f"[{schema_name}] Échec du récap du matin.")` puis `raise` (laisser planter). Le message de l'except général redevient celui des clôtures seules. Les clôtures restent faites avant (aucun changement d'ordre).

## Administration/recap_quotidien.py
7. (vers l.1007-1010) Pose du marqueur protégée contre deux sous-tâches qui se chevauchent : `nombre_de_lignes = Configuration.objects.filter(pk=…).exclude(recap_quotidien_traite_le=aujourd_hui).update(recap_quotidien_traite_le=aujourd_hui)` ; si `nombre_de_lignes == 0` → `return False` (une autre sous-tâche l'a déjà pris). Garde l'ordre calcul → marqueur → envoi. Commentaire FALC. Test : marqueur posé « entre » la lecture et la pose (simuler en posant le marqueur dans un side_effect de preparer, ou équivalent simple) → aucun mail.
8. (vers l.849-853) `destinataires_du_recap` : normaliser D'ABORD les adresses des admins (strip, lower, écarter les vides) ; le repli sur `configuration.email` se fait si CETTE liste nettoyée est vide. Test : un seul admin à e-mail vide → `[configuration.email]`.

## BaseBillet/templates/emails/recap_quotidien.html
9. Le msgid « Ouvrir l'administration » (apostrophe droite, l.51 et l.94) doit reprendre exactement le msgid existant « Ouvrir l’administration » (apostrophe COURBE, cf. BaseBillet/tasks.py:495). Ajuster toute assertion de test qui le cherche.
