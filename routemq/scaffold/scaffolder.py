from __future__ import annotations

import sys
from importlib import import_module
from importlib import metadata
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

SENTINEL_VERSION = '0.13.4'
TEMPLATE_PACKAGE = 'routemq.scaffold.templates'


def run_scaffolder(
    name: str,
    *,
    yes: bool = False,
    with_mysql: bool = False,
    with_redis: bool = False,
    with_queue: bool = False,
    with_docker: bool = False,
    package_manager: str = 'uv',
    no_input: bool = False,
) -> int:
    """Scaffold a new RouteMQ project."""
    target = Path.cwd() / name
    current_dir_target = name == '.'

    if target.exists() and any(target.iterdir()) and not current_dir_target:
        print(f'Error: {target} exists and is not empty', file=sys.stderr)
        return 2

    defaults = {
        'with_mysql': with_mysql,
        'with_redis': with_redis,
        'with_queue': with_queue,
        'with_docker': with_docker,
        'package_manager': package_manager,
    }

    if not yes and not no_input and sys.stdout.isatty():
        from .prompts import gather_choices

        choices = gather_choices(defaults)
    else:
        choices = defaults.copy()

    _normalize_choices(choices)
    project_name = target.resolve().name if current_dir_target else name
    context = _build_context(project_name=project_name, choices=choices)
    template_root = files(TEMPLATE_PACKAGE)

    _copy_tree(template_root / 'base', target, **context)

    if choices['with_mysql']:
        _copy_tree(template_root / 'features' / 'mysql', target, **context)
        _append_fragment(target / '.env', template_root / 'features' / 'mysql' / '.env.fragment', **context)
    if choices['with_redis']:
        _append_fragment(target / '.env', template_root / 'features' / 'redis' / '.env.fragment', **context)
    if choices['with_queue']:
        _copy_tree(template_root / 'features' / 'queue', target, **context)
        _append_fragment(target / '.env', template_root / 'features' / 'queue' / '.env.fragment', **context)
    if choices['with_docker']:
        _copy_tree(template_root / 'features' / 'docker', target, **context)

    _print_success(project_name=project_name, package_manager=choices['package_manager'])
    return 0


def _normalize_choices(choices: dict[str, Any]) -> None:
    choices['package_manager'] = choices.get('package_manager') or 'uv'
    if choices['package_manager'] not in {'uv', 'pip'}:
        raise ValueError('package_manager must be either "uv" or "pip"')

    if choices.get('with_queue') and not (choices.get('with_mysql') or choices.get('with_redis')):
        print('Queue requires Redis or MySQL backend; enabling Redis.')
        choices['with_redis'] = True


def _build_context(project_name: str, choices: dict[str, Any]) -> dict[str, Any]:
    selected_features = [
        feature
        for feature, enabled in (
            ('mysql', choices['with_mysql']),
            ('redis', choices['with_redis']),
            ('queue', choices['with_queue']),
            ('docker', choices['with_docker']),
        )
        if enabled
    ]
    extras = []
    if choices['with_redis']:
        extras.append('redis')

    routemq_version = _get_routemq_version()
    dependency = f'routemq[{",".join(extras)}]>={routemq_version}' if extras else f'routemq>={routemq_version}'

    return {
        'project_name': project_name,
        'package_name': _normalize_package_name(project_name),
        'features': selected_features,
        'feature_list': ', '.join(selected_features) if selected_features else 'base',
        'with_mysql': choices['with_mysql'],
        'with_redis': choices['with_redis'],
        'with_queue': choices['with_queue'],
        'with_docker': choices['with_docker'],
        'queue_connection': 'redis' if choices['with_redis'] else 'database',
        'package_manager': choices['package_manager'],
        'routemq_version': routemq_version,
        'extras': ','.join(extras),
        'dependency': dependency,
    }


def _copy_tree(src_resource_path: Traversable, target_dir: Path, **context: Any) -> None:
    """Copy a resource tree to target_dir, rendering *.j2 files."""
    target_dir.mkdir(parents=True, exist_ok=True)

    for item in src_resource_path.iterdir():
        if item.name in {'__pycache__', '.env.fragment'}:
            continue

        destination = target_dir / item.name
        if item.is_dir():
            _copy_tree(item, destination, **context)
            continue

        if item.name.endswith('.j2'):
            destination = target_dir / item.name[:-3]
            destination.write_text(_render_jinja(item.read_text(), **context), encoding='utf-8')
        else:
            destination.write_bytes(item.read_bytes())


def _append_fragment(env_path: Path, fragment_path: Traversable, **context: Any) -> None:
    fragment = _render_jinja(fragment_path.read_text(), **context)
    with env_path.open('a', encoding='utf-8') as env_file:
        if env_path.stat().st_size > 0:
            env_file.write('\n')
        env_file.write(fragment.rstrip())
        env_file.write('\n')


def _render_jinja(template_string: str, **context: Any) -> str:
    try:
        jinja2 = import_module('jinja2')
    except ImportError as exc:
        raise ImportError('Scaffolding templates require: pip install routemq[cli]') from exc

    return jinja2.Template(template_string).render(**context)


def _get_routemq_version() -> str:
    try:
        return metadata.version('routemq')
    except metadata.PackageNotFoundError:
        return SENTINEL_VERSION


def _normalize_package_name(project_name: str) -> str:
    normalized = project_name.lower().replace('-', '_').replace(' ', '_')
    return ''.join(ch for ch in normalized if ch.isalnum() or ch == '_') or 'routemq_app'


def _print_success(*, project_name: str, package_manager: str) -> None:
    lines = [
        f'Created {project_name}.',
        f'Next: cd {project_name}',
        'Install: uv sync' if package_manager == 'uv' else 'Install: pip install -e .',
        'Run: routemq run',
    ]
    try:
        rich_console = import_module('rich.console')
    except ImportError:
        print('\n'.join(lines))
        return

    console = rich_console.Console()
    console.print('\n'.join(lines), style='green')
