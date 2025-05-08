FROM python:latest

VOLUME /app

WORKDIR /app

RUN pip --quiet install virtualenv

RUN virtualenv --quiet venv

RUN <<END bash

source venv/bin/activate

pip --quiet install git+https://github.com/icann/lgr-core.git@a1f0551ec0c59f009b0ee9f81e4b45f8ea79ed4c

pip --quiet install idna pkgconfig

END

ADD . .

ENTRYPOINT /app/entrypoint.sh
