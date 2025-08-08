FROM python:latest

VOLUME /app

WORKDIR /app

RUN pip --quiet install virtualenv

RUN virtualenv --quiet venv

RUN <<END bash

source venv/bin/activate

pip --quiet install git+https://github.com/icann/lgr-core.git@v6.1.3

pip --quiet install idna pkgconfig

END

ADD . .

ENTRYPOINT /app/entrypoint.sh
