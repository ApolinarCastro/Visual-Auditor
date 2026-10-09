"""Offline contracts for the repository gate; never start MRI or a browser."""
import importlib
import subprocess

import pytest


def policy():
    return importlib.import_module('_mri_differential_precheck')


@pytest.mark.parametrize('path,tracked,status,group,reason', [
    ('logs/audit.log', False, 'PASS', 'runtime_artifacts', None),
    ('data/sessions/session.json', False, 'PASS', 'runtime_artifacts', None),
    ('app/__pycache__/module.cpython-314.pyc', False, 'PASS', 'runtime_artifacts', None),
    ('.pytest_cache/v/cache/nodeids', False, 'PASS', 'runtime_artifacts', None),
    ('data/sample_profile/Default/Cookies', False, 'PASS', 'runtime_artifacts', None),
    ('data/sample_profile/Local State', False, 'PASS', 'runtime_artifacts', None),
    ('data/sample_profile/Default/Extensions/plugin/manifest.json', False, 'BLOCKED', 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'),
    ('data/sample_profile/run.js', False, 'BLOCKED', 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'),
    ('evidence/task/result.json', False, 'PASS', 'evidence', None),
    ('scratch/notes.txt', False, 'PASS', 'scratch', None),
    ('notes.txt', False, 'PASS', 'unknown', None),
    ('app/new.py', False, 'BLOCKED', 'source_changes', 'UNTRACKED_OPERATIONAL_SOURCE'),
    ('app/current.py', True, 'BLOCKED', 'source_changes', 'UNAUTHORIZED_TRACKED_SOURCE_CHANGE'),
    ('tools/unknown.ps1', False, 'BLOCKED', 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'),
    ('settings.toml', False, 'BLOCKED', 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'),
    ('package.json', False, 'BLOCKED', 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'),
    ('.agents/config.toml', False, 'BLOCKED', 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'),
    ('data/sessions/plugin.js', False, 'BLOCKED', 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'),
    ('evidence/task/run.py', False, 'BLOCKED', 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'),
    ('scratch/run.sh', False, 'BLOCKED', 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'),
    ('data/unknown.json', False, 'BLOCKED', 'unknown', 'UNKNOWN_FILE_REQUIRES_ATTRIBUTION'),
    ('logs/audit.log', True, 'PASS', 'runtime_artifacts', None),
    ('evidence/task/result.json', True, 'PASS', 'evidence', None),
    ('app/settings.json', True, 'BLOCKED', 'source_changes', 'UNAUTHORIZED_TRACKED_SOURCE_CHANGE'),
])
def test_classification(path, tracked, status, group, reason):
    result = policy().classify_changes([{'path': path, 'tracked': tracked, 'change': 'M' if tracked else '??'}])
    assert result['status'] == status
    assert result[group][0]['path'] == path
    assert result['blocking_reasons'] == ([] if reason is None else [reason])


def test_clean_source_passes():
    assert policy().classify_changes([])['status'] == 'PASS'


def test_authorization_is_content_bound():
    change = {'path': 'app/current.py', 'tracked': True, 'change': 'M', 'sha256': 'current'}
    assert policy().classify_changes([change], authorized={'app/current.py': 'old'})['status'] == 'BLOCKED'
    assert policy().classify_changes([change], authorized={'app/current.py': 'current'})['status'] == 'PASS'


def test_explicit_non_runtime_disposition_does_not_authorize_new_bytes():
    change = {'path': 'app/retired.py', 'tracked': False, 'change': '??', 'sha256': 'reviewed'}
    result = policy().classify_changes([change], non_runtime={'app/retired.py': 'reviewed'})
    assert result['status'] == 'PASS'
    change['sha256'] = 'different'
    assert policy().classify_changes([change], non_runtime={'app/retired.py': 'reviewed'})['status'] == 'BLOCKED'


def test_symlink_never_trusted_by_runtime_path():
    result = policy().classify_changes([{'path': 'logs/link.txt', 'tracked': False, 'symlink': True}])
    assert result['status'] == 'BLOCKED'


def test_git_inventory_includes_ignored_executable(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / '.gitignore').write_text('logs/\n')
    (tmp_path / 'logs').mkdir()
    (tmp_path / 'logs' / 'run.py').write_text('print(1)\n')
    report = policy().check_worktree(tmp_path)
    assert report['status'] == 'BLOCKED'
    assert any(x['path'] == 'logs/run.py' for x in report['unknown'])


def test_git_runtime_and_evidence_do_not_block(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    for name in ('logs/run.log', 'evidence/task/result.json'):
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{}')
    assert policy().check_worktree(tmp_path)['status'] == 'PASS'


def test_existing_runner_calls_differential_gate(monkeypatch):
    helper = importlib.import_module('_mri_4mp_certification_helper')
    monkeypatch.setattr(helper, 'run_cmd', lambda cmd: 'main' if '--show-current' in cmd else '')
    monkeypatch.setattr(helper, 'check_cmd', lambda cmd: 0)
    monkeypatch.setattr(helper.os.path, 'exists', lambda path: True)
    monkeypatch.setattr(helper, 'check_worktree', lambda: {'status': 'BLOCKED', 'blocking_reasons': ['UNTRACKED_OPERATIONAL_SOURCE']})
    with pytest.raises(SystemExit) as error:
        helper.run_precheck()
    assert error.value.code == helper.EXIT_PRECHECK_BLOCKED
