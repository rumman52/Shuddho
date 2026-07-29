from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from shared.schemas.python_models import AnalyzeMode, Suggestion

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.86
CORRECTOR_ENABLED_ENV_VAR = "SHUDDHO_CORRECTOR_ENABLED"
CORRECTOR_CHECKPOINT_ENV_VAR = "SHUDDHO_CORRECTOR_CHECKPOINT"
CORRECTOR_THRESHOLD_ENV_VAR = "SHUDDHO_CORRECTOR_THRESHOLD"
CORRECTOR_MODEL_URL_ENV_VAR = "SHUDDHO_CORRECTOR_MODEL_URL"
LEGACY_CORRECTOR_THRESHOLD_ENV_VAR = "SHUDDHO_CORRECTOR_CONFIDENCE_THRESHOLD"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHECKPOINT_RELATIVE_PATH = Path("artifacts") / "corrector" / "corrector-base"
DEFAULT_CHECKPOINT_DISPLAY_PATH = DEFAULT_CHECKPOINT_RELATIVE_PATH.as_posix()
CORRECTOR_ENABLED_AUTO_VALUE = "auto"
REQUIRED_CHECKPOINT_FILES = ("metadata.json", "best_model.pt")


@dataclass(frozen=True)
class CorrectorRuntimeStatus:
    enabled: bool
    loaded: bool
    status: str
    reason: str | None
    checkpoint: str | None
    checkpoint_exists: bool
    backend_name: str
    threshold: float


@runtime_checkable
class CorrectorBackend(Protocol):
    backend_name: str
    checkpoint_path: str | None
    confidence_threshold: float

    def suggest(
        self,
        text: str,
        mode: AnalyzeMode,
        *,
        personal_dictionary: list[str] | None = None,
    ) -> list[Suggestion]: ...


class CorrectorService:
    def __init__(
        self,
        backend: CorrectorBackend | None = None,
        *,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        checkpoint_path: str | None = None,
        enabled: bool | None = None,
        status: str | None = None,
        reason: str | None = None,
        checkpoint_exists: bool | None = None,
    ) -> None:
        self.backend = backend
        self.confidence_threshold = confidence_threshold
        self.checkpoint_path = checkpoint_path.strip() if checkpoint_path else None
        self.enabled = self.backend is not None if enabled is None else enabled
        if checkpoint_exists is None:
            _, resolved_checkpoint_path = self._resolve_checkpoint_path(
                self.checkpoint_path
            )
            checkpoint_exists = bool(
                resolved_checkpoint_path and resolved_checkpoint_path.exists()
            )
        self.checkpoint_exists = checkpoint_exists
        if self.backend is not None and status is None:
            status = "ready"
        self.status = status or ("disabled" if not self.enabled else "unavailable")
        self.reason = None if self.status == "ready" else reason

    def is_loaded(self) -> bool:
        return self.backend is not None

    def is_enabled(self) -> bool:
        return self.enabled

    @property
    def backend_name(self) -> str:
        if self.backend is None:
            return "disabled"
        return getattr(self.backend, "backend_name", "corrector_backend")

    def runtime_status(self) -> CorrectorRuntimeStatus:
        return CorrectorRuntimeStatus(
            enabled=self.enabled,
            loaded=self.is_loaded(),
            status=self.status,
            reason=self.reason,
            checkpoint=self.checkpoint_path,
            checkpoint_exists=self.checkpoint_exists,
            backend_name=self.backend_name,
            threshold=self.confidence_threshold,
        )

    def suggest(
        self,
        text: str,
        *,
        mode: AnalyzeMode,
        personal_dictionary: list[str] | None = None,
    ) -> list[Suggestion]:
        if not self.is_loaded():
            return []

        try:
            return list(
                self.backend.suggest(
                    text,
                    mode,
                    personal_dictionary=personal_dictionary,
                )
            )
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            logger.warning(
                "Corrector backend '%s' failed during suggestion generation (%s). Falling back to non-corrector analysis.",
                self.backend_name,
                error,
            )
            return []

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "CorrectorService":
        environment = os.environ if environ is None else environ
        explicit_checkpoint = environment.get(CORRECTOR_CHECKPOINT_ENV_VAR)
        threshold_value = environment.get(CORRECTOR_THRESHOLD_ENV_VAR)
        threshold_env_var = CORRECTOR_THRESHOLD_ENV_VAR
        if threshold_value is None:
            threshold_value = environment.get(LEGACY_CORRECTOR_THRESHOLD_ENV_VAR)
            threshold_env_var = LEGACY_CORRECTOR_THRESHOLD_ENV_VAR

        confidence_threshold = cls._resolve_confidence_threshold(
            threshold_value,
            env_var_name=threshold_env_var,
        )
        enabled_mode = cls._resolve_enabled_mode(
            environment.get(CORRECTOR_ENABLED_ENV_VAR)
        )
        configured_checkpoint = cls._configured_checkpoint_path(explicit_checkpoint)
        normalized_checkpoint_path, resolved_checkpoint_path = (
            cls._resolve_checkpoint_path(configured_checkpoint)
        )
        checkpoint_exists = bool(
            resolved_checkpoint_path and resolved_checkpoint_path.exists()
        )

        logger.info(
            "Corrector environment initialization enabled_mode=%s checkpoint=%s checkpoint_exists=%s threshold=%.2f",
            enabled_mode,
            normalized_checkpoint_path,
            checkpoint_exists,
            confidence_threshold,
        )
        if (
            explicit_checkpoint is None or not explicit_checkpoint.strip()
        ) and not checkpoint_exists:
            logger.warning(
                "%s is not set and the default corrector artifact was not found at '%s'. Set %s or train the local corrector before expecting sentence-level correction.",
                CORRECTOR_CHECKPOINT_ENV_VAR,
                DEFAULT_CHECKPOINT_DISPLAY_PATH,
                CORRECTOR_CHECKPOINT_ENV_VAR,
            )

        if enabled_mode == "false":
            logger.warning(
                "%s is disabled via %s; sentence-level corrector suggestions will be skipped.",
                CORRECTOR_ENABLED_ENV_VAR,
                environment.get(CORRECTOR_ENABLED_ENV_VAR),
            )
            return cls(
                confidence_threshold=confidence_threshold,
                checkpoint_path=normalized_checkpoint_path,
                enabled=False,
                status="disabled",
                reason=f"{CORRECTOR_ENABLED_ENV_VAR}=false disabled corrector startup.",
                checkpoint_exists=checkpoint_exists,
            )

        # Optional model downloads are only a local/ML-profile concern.  In
        # particular, a stale model URL must never make a lightweight Render
        # process perform network I/O while its corrector is explicitly off.
        cls._download_optional_model(
            environment.get(CORRECTOR_MODEL_URL_ENV_VAR),
            resolved_checkpoint_path,
        )
        checkpoint_exists = bool(
            resolved_checkpoint_path and resolved_checkpoint_path.exists()
        )

        return cls.from_checkpoint_path(
            normalized_checkpoint_path,
            confidence_threshold=confidence_threshold,
            enabled=True,
        )

    @classmethod
    def from_checkpoint_path(
        cls,
        checkpoint_path: str | None,
        *,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        enabled: bool = True,
    ) -> "CorrectorService":
        normalized_checkpoint_path, resolved_checkpoint_path = (
            cls._resolve_checkpoint_path(checkpoint_path)
        )
        checkpoint_exists = bool(
            resolved_checkpoint_path and resolved_checkpoint_path.exists()
        )
        if not normalized_checkpoint_path or resolved_checkpoint_path is None:
            logger.warning(
                "No corrector checkpoint path could be resolved; corrector-backed suggestions will be skipped.",
            )
            return cls(
                confidence_threshold=confidence_threshold,
                checkpoint_path=normalized_checkpoint_path,
                enabled=enabled,
                status="missing_checkpoint",
                reason="No corrector checkpoint path is configured.",
                checkpoint_exists=False,
            )

        try:
            backend = cls._load_backend_from_checkpoint(
                normalized_checkpoint_path,
                confidence_threshold=confidence_threshold,
            )
        except FileNotFoundError as error:
            logger.warning(
                "Corrector checkpoint was not found or is incomplete at '%s' (%s); corrector runtime is disabled and analyze requests will stay rule/spell/detector only. Native checkpoints require %s. Fix by setting %s to a valid artifact directory or by training with 'python -m ml.corrector.train --config ml/training/configs/corrector.base.json'.",
                normalized_checkpoint_path,
                error,
                ", ".join(REQUIRED_CHECKPOINT_FILES),
                CORRECTOR_CHECKPOINT_ENV_VAR,
            )
            return cls(
                confidence_threshold=confidence_threshold,
                checkpoint_path=normalized_checkpoint_path,
                enabled=enabled,
                status="missing_checkpoint",
                reason=f"Corrector checkpoint could not be loaded from '{normalized_checkpoint_path}': {error}",
                checkpoint_exists=checkpoint_exists,
            )
        except (ImportError, OSError, RuntimeError, KeyError, ValueError) as error:
            logger.warning(
                "Corrector checkpoint at '%s' could not be loaded (%s); corrector runtime is disabled and analyze requests will stay rule/spell/detector only. Fix the checkpoint contents or point %s to a valid corrector artifact.",
                normalized_checkpoint_path,
                error,
                CORRECTOR_CHECKPOINT_ENV_VAR,
            )
            return cls(
                confidence_threshold=confidence_threshold,
                checkpoint_path=normalized_checkpoint_path,
                enabled=enabled,
                status="load_failed",
                reason=f"Corrector checkpoint failed to load from '{normalized_checkpoint_path}': {error}",
                checkpoint_exists=checkpoint_exists,
            )

        return cls(
            backend=backend,
            confidence_threshold=confidence_threshold,
            checkpoint_path=normalized_checkpoint_path,
            enabled=enabled,
            status="ready",
            checkpoint_exists=checkpoint_exists,
        )

    @classmethod
    def _load_backend_from_checkpoint(
        cls,
        checkpoint_path: str,
        *,
        confidence_threshold: float,
    ) -> CorrectorBackend:
        _, checkpoint_dir = cls._resolve_checkpoint_path(checkpoint_path)
        if checkpoint_dir is None:
            raise FileNotFoundError(checkpoint_path)
        if not checkpoint_dir.exists():
            raise FileNotFoundError(checkpoint_dir)

        missing_files = cls._missing_checkpoint_files(checkpoint_dir)
        if missing_files:
            raise FileNotFoundError(
                f"missing required corrector checkpoint files: {', '.join(missing_files)}"
            )

        from ml.corrector.infer import load_corrector_backend

        return load_corrector_backend(
            checkpoint_dir,
            confidence_threshold=confidence_threshold,
        )

    @staticmethod
    def _missing_checkpoint_files(checkpoint_dir: Path) -> list[str]:
        return [
            filename
            for filename in REQUIRED_CHECKPOINT_FILES
            if not (checkpoint_dir / filename).exists()
        ]

    @staticmethod
    def _resolve_confidence_threshold(value: str | None, *, env_var_name: str) -> float:
        if value is None or not value.strip():
            return DEFAULT_CONFIDENCE_THRESHOLD

        try:
            threshold = float(value)
        except ValueError:
            logger.warning(
                "Invalid %s value '%s'; expected a number between 0.0 and 1.0. Falling back to %.2f.",
                env_var_name,
                value,
                DEFAULT_CONFIDENCE_THRESHOLD,
            )
            return DEFAULT_CONFIDENCE_THRESHOLD

        if not 0.0 <= threshold <= 1.0:
            logger.warning(
                "Out-of-range %s value %.4f; expected a number between 0.0 and 1.0. Falling back to %.2f.",
                env_var_name,
                threshold,
                DEFAULT_CONFIDENCE_THRESHOLD,
            )
            return DEFAULT_CONFIDENCE_THRESHOLD

        return threshold

    @staticmethod
    def _configured_checkpoint_path(explicit_checkpoint: str | None) -> str:
        if explicit_checkpoint and explicit_checkpoint.strip():
            return explicit_checkpoint.strip()
        return DEFAULT_CHECKPOINT_DISPLAY_PATH

    @staticmethod
    def _resolve_checkpoint_path(
        checkpoint_path: str | None,
    ) -> tuple[str | None, Path | None]:
        if checkpoint_path is None or not checkpoint_path.strip():
            return None, None

        normalized_checkpoint_path = checkpoint_path.strip()
        resolved_checkpoint_path = Path(normalized_checkpoint_path)
        if not resolved_checkpoint_path.is_absolute():
            resolved_checkpoint_path = REPO_ROOT / resolved_checkpoint_path
        return normalized_checkpoint_path, resolved_checkpoint_path

    @staticmethod
    def _download_optional_model(
        model_url: str | None, checkpoint_dir: Path | None
    ) -> None:
        if checkpoint_dir is None:
            return
        if model_url is None or not model_url.strip():
            return

        model_path = checkpoint_dir / "best_model.pt"
        if model_path.exists():
            return

        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = model_path.with_suffix(".pt.tmp")
        try:
            logger.info(
                "Downloading optional corrector model from %s to %s because %s is set.",
                model_url,
                model_path,
                CORRECTOR_MODEL_URL_ENV_VAR,
            )
            urllib.request.urlretrieve(
                model_url.strip(), temporary_path
            )  # noqa: S310 - operator-provided model URL
            temporary_path.replace(model_path)
        except (OSError, ValueError, urllib.error.URLError) as error:
            temporary_path.unlink(missing_ok=True)
            logger.warning(
                "Could not download optional corrector model from %s (%s); continuing without the sentence-level corrector.",
                model_url,
                error,
            )

    @staticmethod
    def _resolve_enabled_mode(value: str | None) -> str:
        if value is None or not value.strip():
            return CORRECTOR_ENABLED_AUTO_VALUE

        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return "true"
        if normalized in {"0", "false", "no", "off"}:
            return "false"
        if normalized == CORRECTOR_ENABLED_AUTO_VALUE:
            return CORRECTOR_ENABLED_AUTO_VALUE

        logger.warning(
            "Invalid %s value '%s'; expected auto/true/false. Falling back to auto.",
            CORRECTOR_ENABLED_ENV_VAR,
            value,
        )
        return CORRECTOR_ENABLED_AUTO_VALUE
