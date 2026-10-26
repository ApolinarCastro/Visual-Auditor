"""
app/mri_autonomous/storage_guard.py

Centralized Storage Configuration & Production Write Barrier for MRI.

B-02 REMEDIATION (2026-10-21)
-----------------------------
DEFECT (before): `get_sqlite_path()` resolved the production database and
`assert_write_allowed()` then rejected that very same path, because
`_ALLOW_PRODUCTION_WRITES` defaulted to False and no production code path ever
set it to True. Result: every persistence call raised
ProductionWriteBlockedError, so MRI could never persist its own results.

ROOT CAUSE: the barrier conflated two different questions:
    (a) "is this path the production database?"  (identity)
    (b) "is this process authorized to write?"   (authority)
It answered (b) with a global boolean that nothing ever set, and derived the
production identity from a CWD-relative `.resolve()` computed at import time,
which made the guard's answer depend on the current working directory.

DESIGN (after): explicit, capability-scoped authorization.

  1. Deny by default. No authorization => every write is rejected.
  2. Authorization is granted per-EXACT-DATABASE, never globally, via
     `authorize_database(path, capability, reason)`.
  3. The production database is a uniquely identified object: it is matched by
     device+inode (Windows: st_dev/st_ino via os.stat), not by string suffix,
     so relative/absolute/case variants resolve to the same identity.
  4. Symlinks are resolved before identity comparison; a link that escapes the
     authorized set is rejected. Hardlinked production files share identity and
     are therefore also rejected.
  5. `set_test_mode()` is NOT a production gate. It only ever narrows scope to
     a sandbox directory; it can never authorize the production database.
  6. There is no global "allow everything" switch.

Capabilities (least privilege):
    CAP_READ          - read-only access
    CAP_WRITE_SANDBOX - write to a non-production database (tests/isolated)
    CAP_WRITE_PROD    - write to the canonical production database
"""

import os
import sys
import hmac
import logging
from pathlib import Path
from typing import Optional, Union, Set, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class ProductionWriteBlockedError(RuntimeError):
    """Raised when an unauthorized write to production storage is attempted."""
    pass


class UnauthorizedDatabaseError(ProductionWriteBlockedError):
    """Raised when a database is opened without an explicit authorization grant."""
    pass


class StorageConfig:
    # ── Capabilities ────────────────────────────────────────────────────────
    CAP_READ = "READ"
    CAP_WRITE_SANDBOX = "WRITE_SANDBOX"
    CAP_WRITE_PROD = "WRITE_PROD"

    # ── Canonical production objects ────────────────────────────────────────
    # NOTE: these are resolved lazily against the *repository root*, not the
    # current working directory, so identity does not depend on CWD.
    _REPO_ROOT = Path(__file__).resolve().parents[2]

    PRODUCTION_SQLITE = _REPO_ROOT / "data" / "sqlite" / "visibility.db"
    PRODUCTION_EXPERIENCE = _REPO_ROOT / "data" / "mri_experience.db"
    PRODUCTION_EXPERIENCE_ALT = _REPO_ROOT / "data" / "experience.db"
    PRODUCTION_HISTORY = _REPO_ROOT / "data" / "mri_history.json"
    PRODUCTION_CATEGORIES = _REPO_ROOT / "data" / "mri_categories.json"

    @classmethod
    def _production_objects(cls) -> Tuple[Path, ...]:
        return (
            cls.PRODUCTION_SQLITE,
            cls.PRODUCTION_EXPERIENCE,
            cls.PRODUCTION_EXPERIENCE_ALT,
            cls.PRODUCTION_HISTORY,
            cls.PRODUCTION_CATEGORIES,
        )

    # ── State ───────────────────────────────────────────────────────────────
    _ISOLATED_DIR: Optional[Path] = None
    _TEST_MODE: bool = False
    # Explicit grants, recorded under two stable keys so that a grant remains
    # valid across the "file does not exist yet -> file exists" transition and
    # across path aliases (symlink/hardlink/case variants) of the same object.
    _GRANTS_PATHS: Dict[str, Set[str]] = {}
    _GRANTS_IDENTITIES: Dict[Tuple[int, int], Set[str]] = {}
    # Audit trail of every authorization decision (tamper-evident review aid)
    _AUDIT: list = []

    # ── Identity helpers ────────────────────────────────────────────────────
    @staticmethod
    def _identity(path: Union[str, Path]) -> Optional[Tuple[int, int]]:
        """
        Return a filesystem identity (st_dev, st_ino) for an existing path.

        This is the same mechanism Python's own `os.path.samefile` uses, so two
        different strings pointing at the same file (relative vs absolute,
        symlink vs target, case variants on Windows) produce equal identities.
        Returns None when the file does not exist yet (not-yet-created DB).
        """
        try:
            st = os.stat(str(path))
            return (st.st_dev, st.st_ino)
        except (OSError, ValueError):
            return None

    @classmethod
    def _is_production_object(cls, path: Union[str, Path]) -> bool:
        """
        True iff `path` denotes one of the canonical production objects.

        Matched by filesystem identity when the file exists (robust against
        symlinks/hardlinks/path aliases), and by resolved-path equality when it
        does not exist yet.
        """
        p = Path(path)
        try:
            resolved = p.resolve()
        except (OSError, ValueError):
            resolved = p.absolute()

        for prod in cls._production_objects():
            # Identity comparison first: catches symlinks/hardlinks/aliases.
            ident_p = cls._identity(resolved)
            ident_prod = cls._identity(prod)
            if ident_p is not None and ident_prod is not None:
                if ident_p == ident_prod:
                    return True
            # Path comparison for not-yet-created targets.
            try:
                if resolved == prod.resolve():
                    return True
            except (OSError, ValueError):
                if os.path.normcase(str(resolved)) == os.path.normcase(str(prod)):
                    return True
        return False

    @classmethod
    def _sandbox_root(cls) -> Optional[Path]:
        """
        Effective isolated directory for this process.

        Honours both isolation mechanisms so that env-based isolation
        (`MRI_ENV=TEST` + `MRI_ISOLATED_DB`) behaves like `set_test_mode()`:
          1. explicit sandbox directory passed to set_test_mode()
          2. parent directory of MRI_ISOLATED_DB
          3. default repo-local tmp/mri_sandbox
        Returns None outside test mode, so production is never considered
        "inside a sandbox".
        """
        if cls._ISOLATED_DIR:
            return cls._ISOLATED_DIR
        if not cls.is_test_mode():
            return None
        env_path = os.getenv("MRI_ISOLATED_DB")
        if env_path:
            return Path(env_path).resolve().parent
        return (cls._REPO_ROOT / "tmp" / "mri_sandbox").resolve()

    @classmethod
    def _is_inside_isolated_dir(cls, path: Union[str, Path]) -> bool:
        """True iff `path` is inside the effective isolated directory."""
        iso = cls._sandbox_root()
        if not iso:
            return False
        try:
            target = Path(path).resolve()
            iso = iso.resolve()
        except (OSError, ValueError):
            return False
        try:
            target.relative_to(iso)
            return True
        except ValueError:
            return False

    # ── Authorization API ───────────────────────────────────────────────────
    @staticmethod
    def _path_key(path: Union[str, Path]) -> str:
        """Stable, normalised path key (does not depend on file existence)."""
        try:
            resolved = Path(path).resolve()
        except (OSError, ValueError):
            resolved = Path(os.path.abspath(str(path)))
        return os.path.normcase(str(resolved))

    @staticmethod
    def _id_key(path: Union[str, Path]) -> Optional[Tuple[int, int]]:
        """Filesystem identity key, or None when the file does not exist."""
        return StorageConfig._identity(path)

    @classmethod
    def _caps_for(cls, path: Union[str, Path]) -> Set[str]:
        """
        Union of capabilities granted for `path`.

        Grants are recorded under BOTH a stable normalised-path key and, when
        the file exists, an identity key. Consultation checks both, so:
          * a grant made before the DB file existed still applies afterwards
            (path key), and
          * the same object reached through another name still applies
            (identity key), which is what makes alias escapes visible.
        """
        caps: Set[str] = set(cls._GRANTS_PATHS.get(cls._path_key(path), set()))
        ident = cls._id_key(path)
        if ident is not None:
            caps |= cls._GRANTS_IDENTITIES.get(ident, set())
        return caps

    @classmethod
    def authorize_database(
        cls,
        path: Union[str, Path],
        capability: str,
        reason: str,
    ) -> str:
        """
        Explicitly authorize a capability on ONE exact database.

        This is the ONLY way to enable writes. It is deliberately:
          * per-database (never global),
          * explicit (requires a stated reason),
          * least-privilege (capability-scoped),
          * refusing to authorize the production database for WRITE_PROD unless
            the caller passes an operator-level acknowledgement env var.

        Returns the grant key used internally (identity-based when the file
        exists).
        """
        if capability not in (cls.CAP_READ, cls.CAP_WRITE_SANDBOX, cls.CAP_WRITE_PROD):
            raise ValueError(f"Unknown capability: {capability!r}")

        if not reason or not str(reason).strip():
            raise ValueError("authorize_database requires an explicit non-empty reason")

        resolved = str(Path(path).resolve())

        is_prod = cls._is_production_object(path)

        # Requirement 2 + 5: test/sandbox mode must never authorize production.
        if is_prod and cls.is_test_mode():
            raise ProductionWriteBlockedError(
                f"PRODUCTION WRITE BARRIER: refusing to authorize production object "
                f"'{resolved}' while in test/sandbox mode. Test mode only ever "
                f"narrows scope; it cannot grant production access."
            )

        # Requirement 6: production writes need an explicit operator opt-in.
        if is_prod and capability in (cls.CAP_WRITE_PROD, cls.CAP_WRITE_SANDBOX):
            ack = os.getenv("MRI_AUTHORIZE_PRODUCTION_WRITES", "").strip()
            if ack != "1":
                raise ProductionWriteBlockedError(
                    f"PRODUCTION WRITE BARRIER: '{resolved}' is the production "
                    f"database. Authorizing production writes requires "
                    f"MRI_AUTHORIZE_PRODUCTION_WRITES=1 (operator opt-in). "
                    f"Refusing by default."
                )

        path_key = cls._path_key(path)
        cls._GRANTS_PATHS.setdefault(path_key, set()).add(capability)
        ident = cls._id_key(path)
        if ident is not None:
            cls._GRANTS_IDENTITIES.setdefault(ident, set()).add(capability)
        cls._AUDIT.append(
            {"action": "AUTHORIZE", "path": resolved, "path_key": path_key,
             "identity": ident, "capability": capability, "reason": str(reason),
             "is_production": is_prod, "test_mode": cls.is_test_mode()}
        )
        logger.info(
            "[StorageGuard] AUTHORIZED %s on %s (production=%s, reason=%s)",
            capability, resolved, is_prod, reason,
        )
        return path_key

    @classmethod
    def revoke_database(cls, path: Union[str, Path]) -> None:
        """Revoke all capabilities previously granted on `path`."""
        path_key = cls._path_key(path)
        cls._GRANTS_PATHS.pop(path_key, None)
        ident = cls._id_key(path)
        if ident is not None:
            cls._GRANTS_IDENTITIES.pop(ident, None)
        cls._AUDIT.append({"action": "REVOKE", "path": str(Path(path).resolve())})
        logger.warning("[StorageGuard] REVOKED all grants on %s", path)

    @classmethod
    def granted_capabilities(cls, path: Union[str, Path]) -> Set[str]:
        return cls._caps_for(path)

    @classmethod
    def authorization_audit(cls) -> list:
        return list(cls._AUDIT)

    @classmethod
    def clear_authorizations(cls) -> None:
        """Revoke every grant (used by tests to restore deny-by-default)."""
        cls._GRANTS_PATHS.clear()
        cls._GRANTS_IDENTITIES.clear()
        cls._AUDIT.append({"action": "CLEAR_ALL"})

    # ── Legacy-compatible test/sandbox switch ───────────────────────────────
    @classmethod
    def set_test_mode(cls, enabled: bool = True, sandbox_dir: Optional[Union[str, Path]] = None) -> None:
        """
        Narrow scope to an isolated sandbox directory.

        This NEVER enables production writes (requirement 5). It only changes
        what `get_*_path()` resolves to, and marks the process as test-mode so
        that production objects are refused outright.
        """
        cls._TEST_MODE = enabled
        if enabled:
            if sandbox_dir:
                cls._ISOLATED_DIR = Path(sandbox_dir).resolve()
            else:
                cls._ISOLATED_DIR = (cls._REPO_ROOT / "tmp" / "mri_sandbox").resolve()
            cls._ISOLATED_DIR.mkdir(parents=True, exist_ok=True)
            # Auto-authorize the sandbox: it is non-production by construction,
            # and refusing it would make the isolated pipeline unusable.
            cls.authorize_database(
                cls._ISOLATED_DIR / "visibility.db",
                cls.CAP_WRITE_SANDBOX,
                reason="isolated sandbox auto-grant (set_test_mode)",
            )
        else:
            cls._ISOLATED_DIR = None

    @classmethod
    def is_test_mode(cls) -> bool:
        env_val = os.getenv("MRI_ENV", "").upper()
        return cls._TEST_MODE or env_val in ("TEST", "SANDBOX", "ISOLATED")

    # ── Path resolution ─────────────────────────────────────────────────────
    _SQLITE_OVERRIDE: Optional[Path] = None

    @classmethod
    def set_sqlite_override(cls, path: Optional[Union[str, Path]]) -> None:
        """
        Pin the SQLite database this process serves/writes, independently of
        test mode. Used by the MRI entry point so `run.py mri --db X` actually
        serves X (previously --db only validated the file and the app still
        resolved the production path).
        """
        cls._SQLITE_OVERRIDE = Path(path).resolve() if path is not None else None

    @classmethod
    def get_sqlite_override(cls) -> Optional[Path]:
        return cls._SQLITE_OVERRIDE

    @classmethod
    def get_sqlite_path(cls) -> Path:
        if cls._SQLITE_OVERRIDE is not None:
            return cls._SQLITE_OVERRIDE
        if cls.is_test_mode():
            if cls._ISOLATED_DIR:
                return cls._ISOLATED_DIR / "visibility.db"
            env_path = os.getenv("MRI_ISOLATED_DB")
            if env_path:
                return Path(env_path).resolve()
            return (cls._REPO_ROOT / "tmp" / "mri_sandbox" / "visibility.db").resolve()
        return cls.PRODUCTION_SQLITE

    @classmethod
    def get_aux_dir(cls) -> Path:
        """Bounded directory for auxiliary run files (JSON catalogs, learning DB).

        Order: MRI_AUX_DIR (operator/launcher) -> effective sandbox root ->
        legacy repo tmp/mri_sandbox. Keeping aux files inside the sandbox root
        lets the guard grant them explicitly instead of leaving them outside
        the authorized area (the old failure: UnauthorizedDatabaseError on
        tmp/mri_sandbox/mri_categories.json).
        """
        env_aux = os.getenv("MRI_AUX_DIR")
        if env_aux:
            return Path(env_aux).resolve()
        sandbox = cls._sandbox_root()
        if sandbox is not None:
            return sandbox
        return (cls._REPO_ROOT / "tmp" / "mri_sandbox").resolve()

    @classmethod
    def get_experience_db_path(cls) -> Path:
        if cls.is_test_mode():
            if cls._ISOLATED_DIR:
                return cls._ISOLATED_DIR / "mri_experience.db"
            return cls.get_aux_dir() / "mri_experience.db"
        return cls.PRODUCTION_EXPERIENCE

    @classmethod
    def get_history_json_path(cls) -> Path:
        if cls.is_test_mode():
            if cls._ISOLATED_DIR:
                return cls._ISOLATED_DIR / "mri_history.json"
            return cls.get_aux_dir() / "mri_history.json"
        return cls.PRODUCTION_HISTORY

    @classmethod
    def get_categories_json_path(cls) -> Path:
        if cls.is_test_mode():
            if cls._ISOLATED_DIR:
                return cls._ISOLATED_DIR / "mri_categories.json"
            return cls.get_aux_dir() / "mri_categories.json"
        return cls.PRODUCTION_CATEGORIES

    # ── The barrier itself ──────────────────────────────────────────────────
    @classmethod
    def assert_write_allowed(cls, target_path: Union[str, Path]) -> None:
        """
        Deny-by-default write check.

        A write is permitted ONLY if an explicit grant for this exact database
        exists (CAP_WRITE_SANDBOX or CAP_WRITE_PROD).

        Raises ProductionWriteBlockedError otherwise. Never returns False: the
        fail-closed contract is an exception, so it cannot be ignored by a
        caller that forgets to check a return value.
        """
        p = Path(target_path)
        try:
            resolved = str(p.resolve())
        except (OSError, ValueError):
            resolved = str(p.absolute())

        caps = cls._caps_for(target_path)
        is_prod = cls._is_production_object(target_path)

        # A symlink/alias that resolves onto a production object is production.
        if is_prod and cls.is_test_mode():
            raise ProductionWriteBlockedError(
                f"PRODUCTION WRITE BARRIER ACTIVATED: '{resolved}' resolves to a "
                f"production object and this process is in test/sandbox mode. "
                f"Execution blocked under Controlled Maintenance policy."
            )

        if not caps:
            raise UnauthorizedDatabaseError(
                f"UNAUTHORIZED DATABASE WRITE: no capability granted for "
                f"'{resolved}'. Call StorageConfig.authorize_database(path, "
                f"capability, reason) first. Deny-by-default is in force "
                f"(Controlled Maintenance policy)."
            )

        if is_prod and cls.CAP_WRITE_PROD not in caps:
            raise ProductionWriteBlockedError(
                f"PRODUCTION WRITE BARRIER ACTIVATED: '{resolved}' is the "
                f"production database but only {sorted(caps)} granted; "
                f"CAP_WRITE_PROD is required."
            )

        if cls.CAP_WRITE_SANDBOX in caps and is_prod:
            raise ProductionWriteBlockedError(
                f"PRODUCTION WRITE BARRIER ACTIVATED: CAP_WRITE_SANDBOX cannot "
                f"authorize the production database '{resolved}'."
            )

        logger.debug("[StorageGuard] write ALLOWED on %s (%s)", resolved, sorted(caps))

    @classmethod
    def ensure_writable(cls, target_path: Union[str, Path], reason: str = "MRI persistence",
                        explicit: bool = False) -> None:
        """
        Convenience gate for MRI writers.

        Two — and only two — ways a non-production target becomes writable:

          1. isolated sandbox  : test mode AND target inside the sandbox root
          2. caller declaration: `explicit=True`, meaning the caller passed the
             path in (e.g. ExperienceStore(db_path=...)) rather than letting the
             system resolve a default. This is a per-call declaration of intent,
             not a global switch.

        Production objects are NEVER writable through this helper: they fall
        straight through to `assert_write_allowed`, which demands CAP_WRITE_PROD
        plus the MRI_AUTHORIZE_PRODUCTION_WRITES operator opt-in.
        """
        # Production is decided first and can never be authorized here.
        if cls._is_production_object(target_path):
            cls.assert_write_allowed(target_path)
            return

        if cls.is_test_mode() and cls._is_inside_isolated_dir(target_path):
            if not cls._caps_for(target_path):
                cls.authorize_database(target_path, cls.CAP_WRITE_SANDBOX,
                                       reason=f"{reason} (isolated sandbox)")
        elif explicit:
            if not cls._caps_for(target_path):
                cls.authorize_database(
                    target_path, cls.CAP_WRITE_SANDBOX,
                    reason=f"{reason} (explicit caller-declared non-production database)")

        cls.assert_write_allowed(target_path)

    @classmethod
    def connect_sqlite(cls, target_path: Union[str, Path], mode: str = "rw", **kwargs):
        """
        Validate immediately before opening an SQLite connection, then open it.

        `mode`:
          'rw' - write connection (barrier enforced)
          'ro' - read-only connection (opened via URI mode=ro)
        """
        if mode == "ro":
            uri = Path(target_path).resolve().as_uri() + "?mode=ro"
            import sqlite3
            conn = sqlite3.connect(uri, uri=True, **kwargs)
            conn.execute("PRAGMA query_only = ON;")
            return conn
        cls.assert_write_allowed(target_path)
        import sqlite3
        return sqlite3.connect(str(target_path), **kwargs)


storage_guard = StorageConfig
