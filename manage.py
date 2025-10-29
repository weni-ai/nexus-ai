#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def get_settings_module():
    default_settings = "nexus.settings.nexus"

    command = sys.argv[1] if len(sys.argv) > 1 else None

    if command is None:
        return default_settings

    settings_map = {
        "runserver": default_settings,
        "runcalling": "nexus.settings.calling",
        "runapi": "nexus.settings.router",
    }

    return settings_map.get(command, default_settings)


def main():
    """Run administrative tasks."""
    settings_module = get_settings_module()
    print(settings_module)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
