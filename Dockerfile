FROM python:latest

VOLUME /app

WORKDIR /app

RUN pip --quiet install virtualenv

RUN virtualenv --quiet venv

RUN <<END bash

source venv/bin/activate

pip --quiet install git+https://github.com/icann/lgr-core.git@v7.0.1

pip --quiet install idna pkgconfig

END

ADD . .

ENTRYPOINT /app/entrypoint.sh
