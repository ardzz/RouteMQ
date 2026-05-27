from __future__ import annotations

from importlib import import_module
from typing import Any


def gather_choices(defaults: dict[str, Any]) -> dict[str, Any]:
    """Lazy-import questionary and return the user's scaffold choices."""
    try:
        questionary = import_module('questionary')
    except ImportError:
        raise ImportError('Interactive mode requires: pip install routemq[cli]') from None

    answers = questionary.prompt(
        [
            {
                'type': 'confirm',
                'name': 'with_mysql',
                'message': 'Include MySQL / SQLAlchemy models?',
                'default': defaults['with_mysql'],
            },
            {
                'type': 'confirm',
                'name': 'with_redis',
                'message': 'Include Redis (cache + rate limiting)?',
                'default': defaults['with_redis'],
            },
            {
                'type': 'confirm',
                'name': 'with_queue',
                'message': 'Include background queue + worker?',
                'default': defaults['with_queue'],
            },
            {
                'type': 'confirm',
                'name': 'with_docker',
                'message': 'Include Docker (compose + Makefile)?',
                'default': defaults['with_docker'],
            },
            {
                'type': 'select',
                'name': 'package_manager',
                'message': 'Package manager?',
                'choices': ['uv', 'pip'],
                'default': defaults['package_manager'],
            },
        ]
    )
    if answers is None:
        return defaults.copy()

    if answers.get('with_queue') and not (answers.get('with_mysql') or answers.get('with_redis')):
        print('Queue requires Redis or MySQL backend; enabling Redis.')
        answers['with_redis'] = True
    return answers
