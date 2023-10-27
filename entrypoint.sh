#!/bin/sh
cd $WORKDIR

python /app/manage.py collectstatic --noinput

gunicorn nexus.wsgi --timeout 600 --preload -c /app/gunicorn.conf.py