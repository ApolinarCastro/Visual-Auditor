"""
app/mri_dashboard/mri_entrypoint.py

B-03 remediation (2026-10-21).

PROBLEM
-------
There was no supported, documented way to start MRI. `run.py` (the CLI the
README documents) only drove the legacy VA pipeline and never touched
`app/mri_dashboard`. The only MRI launcher was `lanzar_mri_dashboard.bat`, which
ran `app/mri_dashboard/mri_api.py` directly — binding 0.0.0.0:8055 with no
authentication and no preflight.

WHAT THIS MODULE PROVIDES
-------------------------
`serve()` performs an explicit preflight and then starts the MRI backend:

  1. loads configuration (.env) and validates auth credentials are present
     (fail-closed: refuse to start unauthenticated)
  2. verifies the SQLite database exists, opens read-only, and contains the
     MRI schema (fail fast with an actionable message instead of a traceback)
  3. binds to 127.0.0.1 by default; refuses non-loopback hosts unless the
     operator passes --allow-remote explicitly
  4. reports startup failures with clear messages and a non-zero exit code

Production writes remain denied: MRI is served read-mostly and the storage
barrier from B-02 is untouched.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Tables that must exist for the MRI views to work.
REQUIRED_TABLES = ("mri_runs", "mri_publications", "mri_products", "mri_categories")


class MRIPreflightError(RuntimeError):
    """Raised when the environment is not ready to serve MRI."""


def _mri_db_path() -> Path:
    from app.mri_autonomous.storage_guard import StorageConfig
    return Path(StorageConfig.get_sqlite_path())


def operational_db_path(explicit: Optional[str] = None) -> Path:
    """Resolve the OPERATIONAL (new-audit) database path.

    Order: explicit -> MRI_ISOLATED_DB -> repo default.
    The protected production database is never returned here.
    """
    if explicit:
        return Path(explicit).resolve()
    env = os.getenv("MRI_ISOLATED_DB")
    if env:
        return Path(env).resolve()
    return (Path(__file__).resolve().parents[2]
            / "data" / "sqlite" / "mri_operational" / "visibility.db").resolve()


def ensure_operational_db(explicit: Optional[str] = None) -> bool:
    """Create the operational DB with the OFFICIAL schema initializer.

    - idempotent: an existing database is reused untouched (never overwritten)
    - no historical data is copied
    - returns True when the database is ready
    """
    target = operational_db_path(explicit)
    if target.exists():
        print(f"[MRI] operational DB reused: {target}")
        return True
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        from app.storage.mri_foundation import init_additive_schema
        conn = sqlite3.connect(str(target))
        try:
            init_additive_schema(conn)
            recon = _reconcile_schema_from_reference(conn)
        finally:
            conn.close()
        print(f"[MRI] operational DB created with official schema: {target}")
        print(f"[MRI] schema parity with certified DB: tables+{recon['tables_created']} "
              f"columns+{recon['columns_added']} indexes+{recon['indexes_created']}")
        return True
    except Exception as exc:
        print(f"[MRI] ERROR creating operational DB {target}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def _reconcile_schema_from_reference(conn, reference: Optional[str] = None) -> dict:
    """Bring the operational schema to parity with the CERTIFIED schema.

    The project's additive initializer defines an older shape of
    `mri_publications` / `mri_historical_publications`; current engines write
    columns that only exist in the certified database. This reconciles the
    operational database using the CERTIFIED DDL as the reference:

      - creates missing tables / indexes (DDL only)
      - adds missing columns with ALTER TABLE ADD COLUMN (additive)

    ZERO rows are copied. It never drops or alters existing definitions, so it
    is safe to run on every start.
    """
    ref = reference or os.getenv("MRI_HISTORICAL_DB")
    if not ref:
        ref = str(Path(__file__).resolve().parents[2] / "data" / "sqlite" / "visibility.db")
    ref_path = Path(ref)
    if not ref_path.exists():
        return {"reference": None, "tables_created": 0, "columns_added": 0, "indexes_created": 0}

    added_tables = added_cols = added_idx = 0
    try:
        ref_conn = sqlite3.connect(f"file:{ref_path.as_posix()}?mode=ro", uri=True)
    except Exception:
        return {"reference": str(ref_path), "tables_created": 0, "columns_added": 0,
                "indexes_created": 0}
    try:
        def name_set(db, kind):
            return {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type=? AND sql IS NOT NULL "
                "AND name NOT LIKE 'sqlite_%'", (kind,))}

        op_tables, ref_tables = name_set(conn, "table"), name_set(ref_conn, "table")
        ref_defs = {r[0]: r[1] for r in ref_conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL "
            "AND name NOT LIKE 'sqlite_%'")}

        for t in sorted(ref_tables - op_tables):
            try:
                conn.execute(ref_defs[t])
                added_tables += 1
            except Exception:
                pass

        for t in sorted(ref_tables & name_set(conn, "table")):
            op_cols = {r[1] for r in conn.execute(f"PRAGMA table_info('{t}')")}
            for cid, cname, ctype, notnull, dflt, pk in ref_conn.execute(
                    f"PRAGMA table_info('{t}')"):
                if cname in op_cols:
                    continue
                decl = f"ALTER TABLE \"{t}\" ADD COLUMN \"{cname}\" {ctype or ''}".strip()
                try:
                    conn.execute(decl)
                    added_cols += 1
                except Exception:
                    pass

        op_idx, ref_idx = name_set(conn, "index"), name_set(ref_conn, "index")
        ref_idx_defs = {r[0]: r[1] for r in ref_conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL "
            "AND name NOT LIKE 'sqlite_%'")}
        for i in sorted(ref_idx - op_idx):
            try:
                conn.execute(ref_idx_defs[i])
                added_idx += 1
            except Exception:
                pass
        conn.commit()
    finally:
        ref_conn.close()

    return {"reference": str(ref_path), "tables_created": added_tables,
            "columns_added": added_cols, "indexes_created": added_idx}


def storage_summary() -> dict:
    """Explicit storage selection, reported at startup."""
    op = operational_db_path()
    prot = os.getenv("MRI_HISTORICAL_DB") or str(
        Path(__file__).resolve().parents[2] / "data" / "sqlite" / "visibility.db")
    return {"operational_db": str(op), "protected_db": prot,
            "mode": (os.getenv("MRI_ENV") or "PRODUCTION").upper()}


def preflight(db_path: Optional[Path] = None) -> Tuple[Path, dict]:
    """
    Validate configuration and storage before binding a port.

    Returns (db_path, info). Raises MRIPreflightError with an actionable message.
    """
    # Load configuration from THIS repository root only. Plain load_dotenv()
    # walks up the directory tree and could pick up an unrelated parent .env
    # (observed: a git worktree reading its parent checkout's credentials),
    # which would silently authenticate an isolated instance.
    try:
        from dotenv import load_dotenv
        from app.config.settings import BASE_DIR
        load_dotenv(BASE_DIR / ".env", override=False)
    except Exception:
        pass

    user = os.getenv("DASHBOARD_USER")
    password = os.getenv("DASHBOARD_PASS")
    if not user or not password:
        raise MRIPreflightError(
            "Credenciales no configuradas. Defina DASHBOARD_USER y DASHBOARD_PASS "
            "en el archivo .env (o en el entorno) antes de iniciar MRI. "
            "MRI se niega a arrancar sin autenticación."
        )

    db = Path(db_path) if db_path else _mri_db_path()
    if not db.exists():
        raise MRIPreflightError(
            f"Base de datos MRI no encontrada: {db}\n"
            f"  Verifique que data/sqlite/visibility.db exista, o defina "
            f"MRI_ISOLATED_DB para apuntar a una base de prueba."
        )
    if db.stat().st_size == 0:
        raise MRIPreflightError(
            f"La base de datos MRI está vacía (0 bytes): {db}"
        )

    try:
        conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON;")
    except sqlite3.Error as e:
        raise MRIPreflightError(f"No se pudo abrir la base MRI en modo lectura: {e}")

    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        missing = [t for t in REQUIRED_TABLES if t not in tables]
        if missing:
            raise MRIPreflightError(
                f"La base MRI no tiene el esquema esperado. Faltan tablas: "
                f"{', '.join(missing)}\n  Ruta: {db}"
            )
        n_runs = conn.execute("SELECT COUNT(*) FROM mri_runs").fetchone()[0]
        n_pubs = conn.execute("SELECT COUNT(*) FROM mri_publications").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()

    if integrity != "ok":
        raise MRIPreflightError(f"integrity_check falló en {db}: {integrity}")

    info = {
        "db_path": str(db),
        "db_size": db.stat().st_size,
        "tables": len(tables),
        "runs": n_runs,
        "publications": n_pubs,
        "integrity": integrity,
        "user": user,
    }
    return db, info


def serve(
    host: str = "127.0.0.1",
    port: int = 8055,
    allow_remote: bool = False,
    db_path: Optional[Path] = None,
) -> int:
    """Run the MRI backend. Returns a process exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    if host not in LOOPBACK_HOSTS and not allow_remote:
        print(
            f"[MRI] ERROR: host '{host}' no es loopback. MRI solo debe exponerse "
            f"en 127.0.0.1.\n"
            f"      Si realmente necesita exponerlo en la red, repita con "
            f"--allow-remote (no recomendado).",
            file=sys.stderr,
        )
        return 2

    # Operational DB bootstrap (ONLY for the operator-scoped operational DB).
    # A missing --db path is still a preflight error, as B-03 requires: MRI must
    # never silently create an arbitrary database. Auto-creation applies when
    # MRI_ISOLATED_DB designates the operational DB.
    _op_env = os.getenv("MRI_ISOLATED_DB")
    if _op_env and (db_path is None or
                    Path(db_path).resolve() == Path(_op_env).resolve()):
        if not Path(_op_env).exists():
            if not ensure_operational_db(_op_env):
                print("[MRI] ERROR: no se pudo preparar la base operativa.",
                      file=sys.stderr)
                return 5

    try:
        db, info = preflight(db_path)
    except MRIPreflightError as e:
        print(f"[MRI] ERROR de preflight:\n  {e}", file=sys.stderr)
        logger.error("MRI preflight failed: %s", e)
        return 3

    print("=" * 66)
    print(" MRI — Marketplace Research Intelligence")
    print("=" * 66)
    print(f"  base de datos : {info['db_path']}")
    print(f"  tamaño        : {info['db_size']:,} bytes")
    print(f"  tablas        : {info['tables']}")
    print(f"  corridas      : {info['runs']:,}")
    print(f"  publicaciones : {info['publications']:,}")
    print(f"  integridad    : {info['integrity']}")
    print(f"  usuario       : {info['user']}")
    print(f"  escuchando en : http://{host}:{port}")
    print(f"  autenticación : HTTP Basic (obligatoria)")
    _st = storage_summary()
    print(f"  operativa     : {_st['operational_db']}")
    print(f"  histórica     : {_st['protected_db']} (solo lectura)")
    print("=" * 66)
    print("  Ctrl+C para detener.")

    try:
        import uvicorn
        # Make `--db` authoritative for the served app, not just for preflight.
        if db_path is not None:
            from app.mri_autonomous.storage_guard import StorageConfig
            StorageConfig.set_sqlite_override(db_path)
            logger.info("MRI sqlite override: %s", StorageConfig.get_sqlite_path())
        from app.mri_dashboard.mri_api import app
    except Exception as e:
        print(f"[MRI] ERROR al cargar la aplicación: {e}", file=sys.stderr)
        return 4

    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except OSError as e:
        print(
            f"[MRI] ERROR: no se pudo abrir el puerto {port} en {host}: {e}\n"
            f"      ¿Hay otro proceso usando ese puerto? Pruebe --port <otro>.",
            file=sys.stderr,
        )
        return 5
    except KeyboardInterrupt:
        print("\n[MRI] detenido por el operador.")
    return 0


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(
        prog="run.py mri",
        description="Inicia el dashboard/API de MRI (loopback por defecto).",
    )
    p.add_argument("--host", default="127.0.0.1", help="host de escucha (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8055, help="puerto (default 8055)")
    p.add_argument("--db", default=None, help="ruta explícita a la base SQLite")
    p.add_argument(
        "--allow-remote", action="store_true",
        help="permite un host no-loopback (no recomendado)",
    )
    args = p.parse_args(argv)
    return serve(
        host=args.host,
        port=args.port,
        allow_remote=args.allow_remote,
        db_path=Path(args.db) if args.db else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
