[loggers]
keys=root, gunicorn.error, gunicorn.access

[handlers]
keys=console

[formatters]
keys=generic

[logger_root]
level=DEBUG
handlers=console

[logger_gunicorn.error]
level=ERROR
handlers=console
propagate=0
qualname=/tmp/gunicorn.error

[logger_gunicorn.access]
level=INFO
handlers=console
propagate=0
qualname=/tmp/gunicorn.access

[handler_console]
class=StreamHandler
formatter=generic
args=(sys.stdout, )

[formatter_generic]
format=%(asctime)s [%(process)d] [%(levelname)s] %(message)s
datefmt=%Y-%m-%d %H:%M:%S
class=logging.Formatter