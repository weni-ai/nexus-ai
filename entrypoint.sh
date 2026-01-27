#!/bin/bash

export GUNICORN_APP=${GUNICORN_APP:-"nexus.asgi"}
export GUNICORN_CONF=${GUNICORN_CONF:-"${APP_PATH}/gunicorn.conf.py"}
export GUNICORN_LOG_CONF=${GUNICORN_LOG_CONF:-"${APP_PATH}/gunicorn-logging.conf"}
export LOG_LEVEL=${LOG_LEVEL:-"INFO"}
export CELERY_APP=${CELERY_APP:-"nexus.celery"}
export CELERY_MAX_WORKERS=${CELERY_MAX_WORKERS:-'6'}
export HEALTHCHECK_TIMEOUT=${HEALTHCHECK_TIMEOUT:-"10"}
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


if [[ "start-wsgi" == "$1" ]]; then
    echo "starting server"
    do_gosu "${APP_USER}:${APP_GROUP}" python manage.py collectstatic --noinput
    echo "collectstatic runned start gunicorn"
    do_gosu "${APP_USER}:${APP_GROUP}" exec gunicorn "${GUNICORN_APP}" \
      --name="${APP_NAME}" \
      --chdir="${APP_PATH}" \
      --bind=0.0.0.0:8000 \
      --log-config="${GUNICORN_LOG_CONF}" \
      -c "${GUNICORN_CONF}"
elif [[ "start" == "$1" ]]; then
    do_gosu "${APP_USER}:${APP_GROUP}" python manage.py collectstatic --noinput
    do_gosu "${APP_USER}:${APP_GROUP}" exec daphne -b 0.0.0.0 -p 8000 nexus.asgi:application
elif [[ "celery-worker" == "$1" ]]; then
    celery_queue="celery"
    echo "celery worker"
    if [ "${2}" ] ; then
        celery_queue="${2}"
    fi
    do_gosu "${APP_USER}:${APP_GROUP}" exec celery \
        -A "${CELERY_APP}" --workdir="${PROJECT_PATH}" worker \
        -Q "${celery_queue}" \
        -O fair \
        -l "${LOG_LEVEL}" \
        --autoscale=${CELERY_MAX_WORKERS},1
elif [[ "healthcheck-celery-worker" == "$1" ]]; then
    celery_queue="celery"
    if [ "${2}" ] ; then
        celery_queue="${2}"
    fi
    if pgrep -f "celery.*worker.*-Q.*${celery_queue}" > /dev/null 2>&1; then
        echo "${celery_queue}@${HOSTNAME}: OK"
        exit 0
    else
        if pgrep -f "celery.*worker" > /dev/null 2>&1; then
            echo "${celery_queue}@${HOSTNAME}: OK"
            exit 0
        else
            echo "${celery_queue}@${HOSTNAME}: FAILED - Worker process not found"
            exit 1
        fi
    fi
fi

exec "$@"
