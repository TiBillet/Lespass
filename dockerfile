FROM python:3.11-bullseye

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
USER tibillet

ENV POETRY_NO_INTERACTION=1

## PYTHON
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/home/tibillet/.local/bin:$PATH"

COPY --chown=tibillet:tibillet ./ /DjangoFiles
COPY --chown=tibillet:tibillet ./bashrc /home/tibillet/.bashrc

WORKDIR /DjangoFiles

RUN poetry install

CMD ["bash", "/DjangoFiles/start.sh"]

# docker build -t lespass .
# docker tag lespass tibillet/lespass:alpha0.9
# docker push tibillet/lespass:alpha0.9

# If nightly
# docker tag lespass tibillet/lespass:nightly
# docker push lespass tibillet/lespass:nightly

# If LTS
# docker tag lespass tibillet/lespass:latest
# docker push lespass tibillet/lespass:latest
