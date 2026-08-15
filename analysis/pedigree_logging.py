"""
Structured tracing for the pedigree pipeline.

Every run gets a trace object that records each stage (parse, solve, layout,
route, render, validate) with timings, a snapshot of what went in and out, and
any warnings raised along the way. Traces are written as JSON Lines to
``logs/pedigree/`` so a bad chart can be diagnosed after the fact without
re-running the pipeline.

The console output stays human-readable; the JSONL file is the machine-readable
record the test harness reads back.
"""

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

LOG_ROOT = os.path.join("logs", "pedigree")

# Set VARIANTMIND_PEDIGREE_LOG=0 to silence console output (tests do this).
_CONSOLE = os.environ.get("VARIANTMIND_PEDIGREE_LOG", "1") != "0"


def _json_safe(value: Any, _depth: int = 0) -> Any:
    """Coerce arbitrary values into something json.dumps will accept.

    Protobuf repeated/composite objects come through the Gemini SDK and are not
    JSON-serialisable, so anything unrecognised degrades to its repr rather than
    raising and taking down a render.
    """
    if _depth > 12:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v, _depth + 1) for v in value]
    if hasattr(value, "items"):
        try:
            return {str(k): _json_safe(v, _depth + 1) for k, v in value.items()}
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return {str(k): _json_safe(v, _depth + 1) for k, v in vars(value).items()}
        except Exception:
            pass
    return repr(value)


class PedigreeTrace:
    """Collects the full execution record for one pedigree render."""

    def __init__(self, label: str = "pedigree", run_id: Optional[str] = None,
                 write_to_disk: bool = True):
        self.label = label
        self.run_id = run_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.events: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.started = time.perf_counter()
        self.write_to_disk = write_to_disk
        self._path: Optional[str] = None

        if write_to_disk:
            try:
                os.makedirs(LOG_ROOT, exist_ok=True)
                self._path = os.path.join(LOG_ROOT, f"{self.run_id}.jsonl")
            except Exception:
                # Logging must never be the reason a render fails.
                self.write_to_disk = False

        self.event("run_start", f"Pedigree run '{label}' started", {"run_id": self.run_id})

    # ── recording ──────────────────────────────────────────────────────────

    def event(self, stage: str, message: str, details: Any = None,
              level: str = "info") -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": round((time.perf_counter() - self.started) * 1000, 2),
            "stage": stage,
            "level": level,
            "message": message,
        }
        if details is not None:
            record["details"] = _json_safe(details)

        self.events.append(record)

        if level == "warning":
            self.warnings.append(f"[{stage}] {message}")
        elif level == "error":
            self.errors.append(f"[{stage}] {message}")

        if self._path:
            try:
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record) + "\n")
            except Exception:
                self._path = None

        if _CONSOLE:
            marker = {"info": "  ", "warning": "! ", "error": "X "}.get(level, "  ")
            suffix = ""
            if details is not None:
                try:
                    rendered = json.dumps(_json_safe(details))
                    suffix = f" | {rendered[:300]}"
                except Exception:
                    suffix = ""
            print(f"{marker}[{record['elapsed_ms']:>8.2f}ms] [{stage}] {message}{suffix}",
                  flush=True)

    def warn(self, stage: str, message: str, details: Any = None) -> None:
        self.event(stage, message, details, level="warning")

    def error(self, stage: str, message: str, details: Any = None) -> None:
        self.event(stage, message, details, level="error")

    @contextmanager
    def stage(self, name: str, message: str = "", details: Any = None):
        """Times a pipeline stage and records start/end (or the failure)."""
        start = time.perf_counter()
        self.event(f"{name}:start", message or f"{name} started", details)
        try:
            yield self
        except Exception as exc:
            self.error(f"{name}:failed", f"{type(exc).__name__}: {exc}",
                       {"duration_ms": round((time.perf_counter() - start) * 1000, 2)})
            raise
        else:
            self.event(f"{name}:done", f"{name} completed",
                       {"duration_ms": round((time.perf_counter() - start) * 1000, 2)})

    # ── output ─────────────────────────────────────────────────────────────

    def dump_artifact(self, name: str, payload: Any) -> Optional[str]:
        """Write an intermediate artifact (JSON or text) next to the trace."""
        if not self.write_to_disk:
            return None
        try:
            artifact_dir = os.path.join(LOG_ROOT, self.run_id + "-artifacts")
            os.makedirs(artifact_dir, exist_ok=True)
            if isinstance(payload, str):
                path = os.path.join(artifact_dir, name)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(payload)
            else:
                path = os.path.join(artifact_dir, name if name.endswith(".json") else name + ".json")
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(_json_safe(payload), fh, indent=2)
            self.event("artifact", f"Wrote artifact {name}", {"path": path})
            return path
        except Exception as exc:
            self.warn("artifact", f"Could not write artifact {name}: {exc}")
            return None

    def summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "label": self.label,
            "total_ms": round((time.perf_counter() - self.started) * 1000, 2),
            "events": len(self.events),
            "warnings": self.warnings,
            "errors": self.errors,
            "log_path": self._path,
        }

    def finish(self) -> Dict[str, Any]:
        summary = self.summary()
        self.event("run_end", "Pedigree run finished", {
            "total_ms": summary["total_ms"],
            "warnings": len(self.warnings),
            "errors": len(self.errors),
        })
        return summary


_NULL_TRACE: Optional[PedigreeTrace] = None


def null_trace() -> PedigreeTrace:
    """A trace that records in memory but never touches disk or stdout."""
    global _NULL_TRACE
    if _NULL_TRACE is None:
        _NULL_TRACE = PedigreeTrace("null", write_to_disk=False)
    return _NULL_TRACE


def log_pedigree_step(step_name: str, message: str, details: Any = None):
    """Backwards-compatible shim for the original flat console logger."""
    timestamp = os.environ.get("CURRENT_TIME_STAMP", "LOG")
    if not _CONSOLE:
        return
    detail_str = ""
    if details is not None:
        try:
            detail_str = f" | Details: {json.dumps(_json_safe(details))}"
        except Exception:
            detail_str = ""
    print(f"[{timestamp}] [{step_name}] {message}{detail_str}", flush=True)
