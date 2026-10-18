FROM python:3.11

## UPDATE
RUN apt-get update && apt-get upgrade -y

## POSTGRES CLIENT
RUN mkdir -p /usr/share/man/man1
RUN mkdir -p /usr/share/man/man7
RUN apt-get install -y --no-install-recommends postgresql-client

# supervisor : orchestre gunicorn + daphne + celery dans le conteneur de prod
# (voir supervisor/supervisord.conf, lance par start.sh)
# / supervisor: orchestrates gunicorn + daphne + celery in the prod container
RUN apt-get update && apt-get install -y nano iputils-ping curl borgbackup cron gettext supervisor

## PLAYWRIGHT / CHROMIUM — librairies systeme requises par chrome-headless-shell (tests E2E)
## / System libraries required by Playwright's chrome-headless-shell (E2E tests)
RUN apt-get install -y --no-install-recommends \
    libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 libdbus-1-3 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libxkbcommon0 libasound2 libatspi2.0-0

RUN useradd -ms /bin/bash tibillet

# logs/ est exclu de l'image (.dockerignore), mais LOGGING (settings.py) ouvre ses
# fichiers dans BASE_DIR/logs/ des django.setup() : sans ce dossier, Django ne demarre
# pas dans le conteneur de migration lespass_maj, qui n'a aucun volume. Cree ici, avant
# USER, pour pouvoir le donner a tibillet.
# / logs/ is excluded from the image, but LOGGING opens its files there at django.setup():
# without it, Django does not start in lespass_maj (no volumes). Created before USER.
RUN mkdir -p /DjangoFiles/logs && chown -R tibillet:tibillet /DjangoFiles
USER tibillet

ENV POETRY_NO_INTERACTION=1

## PYTHON
# Version epinglee : poetry.lock est en lock-version 2.1 (Poetry 2 obligatoire), et
# l'installeur prend sinon la derniere version publiee.
# / Pinned version: the installer would otherwise take the latest release.
ENV POETRY_VERSION=2.4.3
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/home/tibillet/.local/bin:$PATH"

WORKDIR /DjangoFiles

# Les dependances AVANT le code. Docker reutilise une couche tant que ce qu'elle copie
# n'a pas change : le venv (plusieurs centaines de Mo) n'est reconstruit, pousse et
# retelecharge que si pyproject.toml ou poetry.lock changent. Une release de code seul ne
# fait voyager que la couche du code. `package-mode = false` (pyproject.toml) : Poetry
# installe les dependances sans avoir besoin du code du projet.
# / Dependencies BEFORE the code, so a code-only release only ships the code layer.
COPY --chown=tibillet:tibillet pyproject.toml poetry.lock /DjangoFiles/
RUN poetry install

COPY --chown=tibillet:tibillet ./ /DjangoFiles
COPY --chown=tibillet:tibillet ./bashrc /home/tibillet/.bashrc

CMD ["bash", "/DjangoFiles/start.sh"]

# Construction et publication d'une release : docker_push_update.sh
# (voir TECH_DOC/SESSIONS/DEPLOIEMENT/SPEC.md).
# / Building and publishing a release: docker_push_update.sh
