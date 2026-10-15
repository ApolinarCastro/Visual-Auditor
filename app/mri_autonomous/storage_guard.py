"""
app/mri_autonomous/storage_guard.py

Centralized Storage Configuration & Production Write Barrier for MRI.
Guarantees absolute filesystem isolation between Test/Sandbox environments and Production.

Enforces:
1. Rejection of writes to production paths when running in Test/Sandbox or without explicit authorization.
2. Standardized environment configuration for all MRI writers:
   - AcquisitionRecoveryRunner
   - ExperienceStore
   - CategoryManager
   - MRI API & Dashboard Runner
"""

import os
from pathlib import Path
from typing import Optional, Union

class ProductionWriteBlockedError(RuntimeError):
    """Raised when an unauthorized write to production storage is attempted."""
    pass


class StorageConfig:
    # Canonical production file targets (relative or absolute)
    PRODUCTION_SQLITE = Path("data/sqlite/visibility.db").resolve()
    PRODUCTION_EXPERIENCE = Path("data/mri_experience.db").resolve()
    PRODUCTION_EXPERIENCE_ALT = Path("data/experience.db").resolve()
    PRODUCTION_HISTORY = Path("data/mri_history.json").resolve()
    PRODUCTION_CATEGORIES = Path("data/mri_categories.json").resolve()

    _ISOLATED_DIR: Optional[Path] = None
    _TEST_MODE: bool = False
    _ALLOW_PRODUCTION_WRITES: bool = False

    @classmethod
    def set_test_mode(cls, enabled: bool = True, sandbox_dir: Optional[Union[str, Path]] = None) -> None:
        """Enable or disable test mode and set isolated sandbox directory."""
        cls._TEST_MODE = enabled
        if enabled:
            cls._ALLOW_PRODUCTION_WRITES = False
            if sandbox_dir:
                cls._ISOLATED_DIR = Path(sandbox_dir).resolve()
                cls._ISOLATED_DIR.mkdir(parents=True, exist_ok=True)
            else:
                cls._ISOLATED_DIR = Path("tmp/mri_sandbox").resolve()
                cls._ISOLATED_DIR.mkdir(parents=True, exist_ok=True)
        else:
            cls._ISOLATED_DIR = None

    @classmethod
    def is_test_mode(cls) -> bool:
        env_val = os.getenv("MRI_ENV", "").upper()
        return cls._TEST_MODE or env_val in ("TEST", "SANDBOX", "ISOLATED")

    @classmethod
    def get_sqlite_path(cls) -> Path:
        if cls.is_test_mode():
            if cls._ISOLATED_DIR:
                return cls._ISOLATED_DIR / "visibility.db"
            env_path = os.getenv("MRI_ISOLATED_DB")
            if env_path:
                return Path(env_path).resolve()
            return Path("tmp/mri_sandbox/visibility.db").resolve()
        return cls.PRODUCTION_SQLITE

    @classmethod
    def get_experience_db_path(cls) -> Path:
        if cls.is_test_mode():
            if cls._ISOLATED_DIR:
                return cls._ISOLATED_DIR / "mri_experience.db"
            return Path("tmp/mri_sandbox/mri_experience.db").resolve()
        return cls.PRODUCTION_EXPERIENCE

    @classmethod
    def get_history_json_path(cls) -> Path:
        if cls.is_test_mode():
            if cls._ISOLATED_DIR:
                return cls._ISOLATED_DIR / "mri_history.json"
            return Path("tmp/mri_sandbox/mri_history.json").resolve()
        return cls.PRODUCTION_HISTORY

    @classmethod
    def get_categories_json_path(cls) -> Path:
        if cls.is_test_mode():
            if cls._ISOLATED_DIR:
                return cls._ISOLATED_DIR / "mri_categories.json"
            return Path("tmp/mri_sandbox/mri_categories.json").resolve()
        return cls.PRODUCTION_CATEGORIES

    @classmethod
    def assert_write_allowed(cls, target_path: Union[str, Path]) -> None:
        """
        Validates whether writing to target_path is allowed.
        Raises ProductionWriteBlockedError if target_path points to production storage
        or falls outside the authorized sandbox when in test mode.
        """
        raw_str = str(target_path).replace("\\", "/").lower()
        p = Path(target_path).resolve()
        norm_p = str(p).replace("\\", "/").lower()

        # Basenames of production files
        PROD_BASENAMES = {
            "visibility.db",
            "mri_experience.db",
            "experience.db",
            "mri_history.json",
            "mri_categories.json"
        }

        # Check if target matches canonical production objects regardless of CWD
        target_name = p.name.lower()
        has_data_dir = (
            "/data/" in norm_p
            or raw_str.startswith("data/")
            or raw_str.startswith("./data/")
            or raw_str.startswith(".\\data\\")
        )
        is_prod_target = (
            p in (
                cls.PRODUCTION_SQLITE,
                cls.PRODUCTION_EXPERIENCE,
                cls.PRODUCTION_EXPERIENCE_ALT,
                cls.PRODUCTION_HISTORY,
                cls.PRODUCTION_CATEGORIES
            )
            or (target_name in PROD_BASENAMES and has_data_dir)
            or any(
                raw_str == f"data/{b}"
                or raw_str == f"data/sqlite/{b}"
                or raw_str == f"data\\{b}"
                or raw_str == f"data\\sqlite\\{b}"
                or raw_str.endswith(f"/data/{b}")
                or raw_str.endswith(f"/data/sqlite/{b}")
                or raw_str.endswith(f"\\data\\{b}")
                or raw_str.endswith(f"\\data\\sqlite\\{b}")
                for b in PROD_BASENAMES
            )
        )

        if cls.is_test_mode():
            # If in test mode, writing to any production target is strictly forbidden
            if is_prod_target:
                raise ProductionWriteBlockedError(
                    f"PRODUCTION WRITE BARRIER ACTIVATED: Attempted unauthorized write to production target '{target_path}'. "
                    f"Execution blocked under Controlled Maintenance policy."
                )
            # If an isolated sandbox directory is configured, any target that attempts to write to data/
            # or has a production basename outside the sandbox is strictly blocked
            if cls._ISOLATED_DIR:
                iso_norm = str(cls._ISOLATED_DIR).replace("\\", "/").lower()
                if not (norm_p.startswith(iso_norm + "/") or norm_p == iso_norm):
                    if is_prod_target or target_name in PROD_BASENAMES or has_data_dir:
                        raise ProductionWriteBlockedError(
                            f"PRODUCTION WRITE BARRIER ACTIVATED: Target '{target_path}' is outside isolated sandbox '{cls._ISOLATED_DIR}'. "
                            f"Execution blocked under Controlled Maintenance policy."
                        )
        elif not cls._ALLOW_PRODUCTION_WRITES:
            if is_prod_target:
                raise ProductionWriteBlockedError(
                    f"PRODUCTION WRITE BARRIER ACTIVATED: Attempted unauthorized write to production target '{target_path}'. "
                    f"Execution blocked under Controlled Maintenance policy."
                )

storage_guard = StorageConfig
