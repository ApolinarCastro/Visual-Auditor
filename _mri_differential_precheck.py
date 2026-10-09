"""Read-only repository gate. Policy does not trust file age or global counts."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess


EXECUTABLE = {'.py', '.pyw', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx',
              '.ps1', '.bat', '.cmd', '.sh', '.exe', '.dll', '.so', '.pyd'}
CONFIG = {'.toml', '.yaml', '.yml', '.ini', '.cfg', '.pth'}
CRITICAL_NAMES = {'.gitignore', '.gitattributes', '.gitmodules', 'package.json',
                  'package-lock.json', 'requirements.txt', 'uv.lock', 'poetry.lock',
                  'dockerfile', 'makefile', 'agents.md', 'svmp.xlsx',
                  'actualización masiva de productos.xlsx'}
PASSIVE = {'.txt', '.md', '.rst', '.pdf', '.docx', '.png', '.jpg', '.jpeg', '.svg'}
RUNTIME_ROOTS = {'logs', 'debug_screenshots', '.pytest_cache'}
RUNTIME_SUFFIXES = {'.log', '.tmp', '.png', '.jpg', '.jpeg', '.json', '.db',
                    '.sqlite', '.sqlite3', '.db-wal', '.db-shm'}
BROWSER_STORAGE_SUFFIXES = {'', '.json', '.log', '.ldb', '.dat', '.pma', '.bak',
                            '.sqlite', '.db', '.journal'}
REPORT_SUFFIXES = {'.json', '.jsonl', '.csv', '.txt', '.md', '.log', '.png', '.jpg', '.html'}


def classify_changes(changes, *, authorized=None, non_runtime=None):
    """Explicit caller-supplied path/hash decisions; never loaded from untrusted files.

    authorized permits exact tracked task edits. non_runtime attributes reviewed
    untracked backups/diagnostics. Neither is populated from an old inventory.
    """
    authorized, non_runtime = authorized or {}, non_runtime or {}
    result = {k: [] for k in ('source_changes', 'runtime_artifacts', 'evidence', 'scratch', 'unknown')}
    reasons = []
    for change in changes:
        item = dict(change)
        path = PurePosixPath(item['path'].replace('\\', '/'))
        parts = tuple(p.lower() for p in path.parts)
        suffix, name = path.suffix.lower(), path.name.lower()
        critical = (suffix in CONFIG or name in CRITICAL_NAMES or name.startswith('.env')
                    or name.startswith('requirements') or 'logica_operacional' in parts
                    or 'extensions' in parts
                    or (parts and parts[0] == 'app' and suffix == '.json'))
        executable = suffix in EXECUTABLE
        source_location = bool(parts) and (parts[0] in {'app', 'tests'} or len(parts) == 1)
        digest = item.get('sha256')
        reason = None
        if item.get('symlink') or path.is_absolute() or '..' in parts:
            group, reason = 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'
        elif digest and not item.get('tracked') and non_runtime.get(item['path']) == digest:
            group = 'scratch'
            item['attribution'] = 'EXPLICIT_NON_RUNTIME_CONTENT_HASH'
        elif executable or critical:
            if item.get('tracked') or (executable and source_location):
                group = 'source_changes'
                if not (item.get('tracked') and digest and authorized.get(item['path']) == digest):
                    reason = ('UNAUTHORIZED_TRACKED_SOURCE_CHANGE' if item.get('tracked')
                              else 'UNTRACKED_OPERATIONAL_SOURCE')
            else:
                group, reason = 'unknown', 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'
        elif parts and parts[0] == 'evidence' and suffix in REPORT_SUFFIXES:
            group = 'evidence'
        elif (('__pycache__' in parts and suffix == '.pyc') or
              (parts and parts[0] == '.pytest_cache' and suffix in {'', '.tag', '.md'}) or
              (len(parts) > 2 and parts[0] == 'data' and 'profile' in parts[1]
               and suffix in BROWSER_STORAGE_SUFFIXES) or
              (parts and parts[0] in RUNTIME_ROOTS and suffix in RUNTIME_SUFFIXES) or
              (len(parts) > 2 and parts[:2] in {('data', 'sessions'), ('data', 'sqlite')}
               and suffix in RUNTIME_SUFFIXES)):
            group = 'runtime_artifacts'
        elif suffix in PASSIVE:
            group = 'scratch' if parts and parts[0] == 'scratch' else 'unknown'
            item['policy'] = 'PASSIVE_DOCUMENT_NOT_RUNTIME_INPUT'
        else:
            group, reason = 'unknown', 'UNKNOWN_FILE_REQUIRES_ATTRIBUTION'
        # Evidence executables are unknown risks, never production source by location.
        if parts and parts[0] == 'evidence' and (executable or critical):
            group = 'unknown'
            reason = 'UNKNOWN_EXECUTABLE_OR_CRITICAL_CONFIG'
        item['blocking_reason'] = reason
        result[group].append(item)
        if reason and reason not in reasons:
            reasons.append(reason)
    result.update(status='BLOCKED' if reasons else 'PASS', blocking_reasons=reasons)
    return result


def check_worktree(root='.', *, authorized=None, non_runtime=None):
    """Use NUL-delimited Git paths, including ignored files; never read secrets."""
    root = Path(root)

    def git(*args):
        return subprocess.check_output(['git', '--no-optional-locks', '-C', str(root), *args])

    records = git('status', '--porcelain=v1', '-z', '--untracked-files=all').decode('utf-8', 'surrogateescape').split('\0')
    changes = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        code, path = record[:2], record[3:]
        changes.append({'path': path, 'change': code, 'tracked': code != '??'})
        if 'R' in code or 'C' in code:
            # Check both endpoints: a rename must not hide a source deletion.
            old = records[index]
            index += 1
            changes.append({'path': old, 'change': 'D', 'tracked': True})
    known = {c['path'] for c in changes}
    for path in git('ls-files', '--others', '--ignored', '--exclude-standard', '-z').decode('utf-8', 'surrogateescape').split('\0'):
        if path and path not in known:
            changes.append({'path': path, 'change': '!!', 'tracked': False})
    hash_paths = set(authorized or {}) | set(non_runtime or {})
    for item in changes:
        path = root / item['path']
        item['symlink'] = path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent)
        if item['path'] in hash_paths and path.is_file() and not item['symlink']:
            item['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return classify_changes(changes, authorized=authorized, non_runtime=non_runtime)


if __name__ == '__main__':
    report = check_worktree()
    print(json.dumps(report, ensure_ascii=True, indent=2))
    raise SystemExit(0 if report['status'] == 'PASS' else 2)
