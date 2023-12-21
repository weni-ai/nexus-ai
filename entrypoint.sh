#!/bin/bash

export GUNICORN_APP=${GUNICORN_APP:-"nexus.wsgi"}
export CELERY_APP=${CELERY_APP:-"app.wsgi:celery"}
export GUNICORN_LOG_CONF=${GUNICORN_LOG_CONF:-"${APP_PATH}/docker/gunicorn/gunicorn-logging.conf"}
export GUNICORN_CONF=${GUNICORN_CONF:-"${APP_PATH}/gunicorn.conf.py"}
export LOG_LEVEL=${LOG_LEVEL:-"INFO"}
#export GUNICORN_CONF=${GUNICORN_CONF:-"python:app.gunicorn"

do_gosu(){
    user="$1"
    shift 1

    is_exec="false"
    if [ "$1" = "exec" ]; then
        is_exec="true"
        shift 1
    fi

    if [ "$(id -u)" = "0" ]; then
        if [ "${is_exec}" = "true" ]; then
            exec gosu "${user}" "$@"
        else
            gosu "${user}" "$@"
            return "$?"
        fi
    else
        if [ "${is_exec}" = "true" ]; then
            exec "$@"
        else
            eval '"$@"'
            return "$?"
        fi
    fi
}


if [[ "start" == "$1" ]]; then
    echo "starting server"
    do_gosu "${APP_USER}:${APP_GROUP}" python manage.py collectstatic --noinput
    echo "collectstatic runned start gunicorn"
    # do_gosu "${APP_USER}:${APP_GROUP}" exec gunicorn "${GUNICORN_APP}" \
    #   --name="${APP_NAME}" \
    #   --chdir="${APP_PATH}" \
    #   --bind=0.0.0.0:8080 \
    #   --log-config="${GUNICORN_LOG_CONF}" \
    #   -c "${GUNICORN_CONF}"
    do_gosu "${APP_USER}:${APP_GROUP}" exec gunicorn "${GUNICORN_APP}" -c "${GUNICORN_CONF}"
elif [ "celery-worker" == "$1" ] ; then
    celery_queue="celery"
    if [ "${2}" ] ; then
        celery_queue="${2}"
    fi
    do_gosu "${APP_USER}:${APP_GROUP}" exec celery \
        -A "${CELERY_APP}" --workdir="${APP_PATH}" worker \
        -Q "${celery_queue}" \
        -O fair \
        -l "${LOG_LEVEL}" \
        --autoscale=4,1
fi

exec "$@"
