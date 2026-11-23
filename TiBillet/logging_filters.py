"""
Filtres de logs du projet.
/ Project log filters.

LOCALISATION : TiBillet/logging_filters.py

Branche dans le dictionnaire LOGGING de TiBillet/settings.py (cle `filters`).
Celery lit le meme dictionnaire (TiBillet/celery.py, signal setup_logging).
/ Plugged into the LOGGING dict of settings.py. Celery reads the same dict.
"""

import logging


# Taches lancees en boucle par Celery beat, pour chaque lieu, plusieurs fois par
# minute. Leurs lignes « received » et « succeeded » font des dizaines de milliers
# de lignes par jour et noient les autres logs. Leurs ECHECS restent affiches :
# Celery les ecrit en ERROR, et ce filtre ne retire que les niveaux sous WARNING.
# / Beat tasks run per venue several times a minute. Only their routine
#   received/succeeded lines are dropped; failures (ERROR) still show.
TACHES_SANS_LOG_DE_ROUTINE = [
    "comptabilite.tasks.generer_les_clotures_automatiques_du_lieu",
]

# Les deux loggers de Celery qui ecrivent « received » et « succeeded ».
# / The two Celery loggers that write "received" and "succeeded".
LOGGERS_CELERY_DE_ROUTINE = [
    "celery.app.trace",
    "celery.worker.strategy",
]


class RetireLesLogsDeRoutineDesTachesCelery(logging.Filter):
    """
    Retire les lignes « Task ... received » et « Task ... succeeded » des taches
    listees dans TACHES_SANS_LOG_DE_ROUTINE. Toutes les autres lignes passent.
    / Drops the routine received/succeeded lines of the listed tasks only.

    Celery passe le nom de la tache dans record.args (un dict avec la cle « name »),
    pas dans le texte : on le lit la, sans analyser le message.
    / Celery passes the task name in record.args (a dict), not in the text.
    """

    def filter(self, record):
        ligne_venant_de_celery = record.name in LOGGERS_CELERY_DE_ROUTINE
        if not ligne_venant_de_celery:
            return True

        # Un avertissement ou une erreur passe toujours.
        # / A warning or an error always goes through.
        if record.levelno >= logging.WARNING:
            return True

        arguments_du_message = record.args
        if not isinstance(arguments_du_message, dict):
            return True

        nom_de_la_tache = arguments_du_message.get("name")
        tache_de_routine = nom_de_la_tache in TACHES_SANS_LOG_DE_ROUTINE
        if tache_de_routine:
            return False

        return True
