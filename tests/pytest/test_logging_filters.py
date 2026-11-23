"""
Tests du filtre qui retire les logs de routine des taches Celery en boucle.
/ Tests of the filter that drops routine logs of looping Celery tasks.

LOCALISATION : tests/pytest/test_logging_filters.py
Code teste : TiBillet/logging_filters.py

SIMULATIONS
- Les lignes de log sont fabriquees a la main avec logging.LogRecord, comme Celery
  les fabrique : le nom de la tache est dans record.args (un dict).
  Aucun worker Celery, aucune base de donnees.
/ Log records are built by hand, the way Celery builds them. No worker, no database.
"""

import logging

from TiBillet.logging_filters import RetireLesLogsDeRoutineDesTachesCelery


TACHE_DE_ROUTINE = "comptabilite.tasks.generer_les_clotures_automatiques_du_lieu"
AUTRE_TACHE = "BaseBillet.tasks.send_email_generique"
MESSAGE_SUCCES_CELERY = (
    "Task %(name)s[%(id)s] succeeded in %(runtime)ss: %(return_value)s"
)


def fabriquer_une_ligne_celery(nom_du_logger, niveau, nom_de_la_tache):
    """
    Fabrique une ligne de log comme celles de Celery.
    / Builds a log record like Celery's.
    """
    arguments_comme_celery = {
        "name": nom_de_la_tache,
        "id": "id-de-test",
        "runtime": 0.1,
        "return_value": None,
    }
    return logging.LogRecord(
        name=nom_du_logger,
        level=niveau,
        pathname=__file__,
        lineno=1,
        msg=MESSAGE_SUCCES_CELERY,
        args=(arguments_comme_celery,),
        exc_info=None,
    )


def test_le_succes_d_une_tache_de_routine_est_retire():
    """Le « succeeded » de la tache des clotures ne sort pas. / Routine success is dropped."""
    filtre = RetireLesLogsDeRoutineDesTachesCelery()
    ligne = fabriquer_une_ligne_celery(
        "celery.app.trace", logging.INFO, TACHE_DE_ROUTINE
    )
    assert filtre.filter(ligne) is False


def test_la_reception_d_une_tache_de_routine_est_retiree():
    """Le « received » de la tache des clotures ne sort pas. / Routine received is dropped."""
    filtre = RetireLesLogsDeRoutineDesTachesCelery()
    ligne = fabriquer_une_ligne_celery(
        "celery.worker.strategy", logging.INFO, TACHE_DE_ROUTINE
    )
    assert filtre.filter(ligne) is False


def test_l_echec_d_une_tache_de_routine_reste_affiche():
    """Une erreur de la tache des clotures sort toujours. / Routine task errors still show."""
    filtre = RetireLesLogsDeRoutineDesTachesCelery()
    ligne = fabriquer_une_ligne_celery(
        "celery.app.trace", logging.ERROR, TACHE_DE_ROUTINE
    )
    assert filtre.filter(ligne) is True


def test_le_succes_d_une_autre_tache_reste_affiche():
    """Le « succeeded » des autres taches sort toujours. / Other tasks still log success."""
    filtre = RetireLesLogsDeRoutineDesTachesCelery()
    ligne = fabriquer_une_ligne_celery("celery.app.trace", logging.INFO, AUTRE_TACHE)
    assert filtre.filter(ligne) is True


def test_une_ligne_qui_ne_vient_pas_de_celery_reste_affichee():
    """Un log applicatif n'est jamais retire. / An application log is never dropped."""
    filtre = RetireLesLogsDeRoutineDesTachesCelery()
    ligne = logging.LogRecord(
        name="BaseBillet.views",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message applicatif",
        args=(),
        exc_info=None,
    )
    assert filtre.filter(ligne) is True
