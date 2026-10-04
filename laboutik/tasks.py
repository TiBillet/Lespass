# laboutik/tasks.py
# Taches Celery pour l'app LaBoutik.
# Celery tasks for the LaBoutik app.
#
# Import des taches d'impression pour que Celery autodiscover les trouve.
# Les taches sont definies dans laboutik/printing/tasks.py mais Celery
# ne scanne que laboutik/tasks.py (pas les sous-modules).
# / Import printing tasks so Celery autodiscover finds them.
# Tasks are defined in laboutik/printing/tasks.py but Celery
# only scans laboutik/tasks.py (not submodules).
#
# Les clotures de caisse (J, H, M, A) et leurs e-mails sont des taches de
# `comptabilite/tasks.py`, planifiees par `TiBillet/celery.py`
# (cron_clotures_automatiques).
# / Register closures and their e-mails are comptabilite/tasks.py tasks.
from laboutik.printing.tasks import imprimer_async, imprimer_commande  # noqa: F401
