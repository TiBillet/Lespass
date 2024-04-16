FROM python:3.11-bullseye

## UPDATE
RUN apt-get update && apt-get upgrade -y

## POSTGRES CLIENT
RUN mkdir -p /usr/share/man/man1
RUN mkdir -p /usr/share/man/man7
RUN apt-get install -y --no-install-recommends postgresql-client

RUN apt-get install -y nano iputils-ping curl borgbackup cron

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
