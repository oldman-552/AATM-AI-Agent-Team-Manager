"""Local resource monitoring for adaptive concurrency.

Only standard-library, local measurements are used: CPU load averages, memory
via ``/proc/meminfo`` (Linux) or ``os.sysconf`` fallbacks, and free disk space
for the AATM data directory. Nothing is uploaded and no provider is contacted.

The system resources endpoint exposes a bounded recommendation and never
changes a run. Separately, the orchestrator can apply a resource-based reduction
to its dispatch batch when ``AATM_ADAPTIVE_CONCURRENCY`` is explicitly enabled;
that reduction never exceeds the operator's configured cap.
"""

import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CPU_CEILING = 4
CPU_FLOOR = 1
MEMORY_PRESSURE_RATIO = 0.9
DISK_PRESSURE_RATIO = 0.95


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: float | None
    load_average_1m: float | None
    cpu_count: int
    memory_total_mb: float | None
    memory_available_mb: float | None
    memory_used_ratio: float | None
    disk_total_gb: float | None
    disk_free_gb: float | None
    disk_used_ratio: float | None
    measured_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "cpu_percent": None if self.cpu_percent is None else round(self.cpu_percent, 2),
            "load_average_1m": None if self.load_average_1m is None else round(self.load_average_1m, 2),
            "cpu_count": self.cpu_count,
            "memory_total_mb": None if self.memory_total_mb is None else round(self.memory_total_mb, 1),
            "memory_available_mb": None if self.memory_available_mb is None else round(self.memory_available_mb, 1),
            "memory_used_ratio": None if self.memory_used_ratio is None else round(self.memory_used_ratio, 3),
            "disk_total_gb": None if self.disk_total_gb is None else round(self.disk_total_gb, 2),
            "disk_free_gb": None if self.disk_free_gb is None else round(self.disk_free_gb, 2),
            "disk_used_ratio": None if self.disk_used_ratio is None else round(self.disk_used_ratio, 3),
            "measured_at": self.measured_at,
        }


def _memory_info() -> tuple[float | None, float | None]:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            values: dict[str, float] = {}
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts:
                    values[key.strip()] = float(parts[0]) / 1024.0  # kB → MB
            total = values.get("MemTotal")
            available = values.get("MemAvailable")
            if total and available is not None:
                return total, available
        except (OSError, ValueError):
            pass
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        total = os.sysconf("SC_PHYS_PAGES") * page / (1024 * 1024)
        return total, None
    except (ValueError, OSError, AttributeError):
        return None, None


def _load_average() -> float | None:
    try:
        return float(os.getloadavg()[0])
    except (OSError, AttributeError):
        return None


def sample_resources(data_dir: Path | None = None) -> ResourceSnapshot:
    cpu_count = os.cpu_count() or 1
    load = _load_average()
    cpu_percent = None
    if load is not None:
        cpu_percent = max(0.0, min(100.0, (load / cpu_count) * 100.0))
    total_mb, available_mb = _memory_info()
    used_ratio = None
    if total_mb and available_mb is not None and total_mb > 0:
        used_ratio = max(0.0, min(1.0, 1.0 - (available_mb / total_mb)))
    disk_total = disk_free = disk_used = None
    target = data_dir or Path.cwd()
    try:
        usage = shutil.disk_usage(str(target))
        disk_total = usage.total / (1024 ** 3)
        disk_free = usage.free / (1024 ** 3)
        if usage.total:
            disk_used = usage.used / usage.total
    except OSError:
        pass
    return ResourceSnapshot(
        cpu_percent=cpu_percent,
        load_average_1m=load,
        cpu_count=cpu_count,
        memory_total_mb=total_mb,
        memory_available_mb=available_mb,
        memory_used_ratio=used_ratio,
        disk_total_gb=disk_total,
        disk_free_gb=disk_free,
        disk_used_ratio=disk_used,
        measured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def recommend_concurrency(
    snapshot: ResourceSnapshot,
    *,
    configured_max: int,
    in_flight: int = 0,
) -> dict[str, object]:
    """Recommend a bounded concurrency without changing live configuration."""
    reasons: list[str] = []
    recommended = max(CPU_FLOOR, min(configured_max, CPU_CEILING, snapshot.cpu_count))

    if snapshot.memory_used_ratio is not None and snapshot.memory_used_ratio >= MEMORY_PRESSURE_RATIO:
        recommended = CPU_FLOOR
        reasons.append(
            f"Memory pressure at {snapshot.memory_used_ratio:.0%} (threshold {MEMORY_PRESSURE_RATIO:.0%}); recommend the floor."
        )
    if snapshot.disk_used_ratio is not None and snapshot.disk_used_ratio >= DISK_PRESSURE_RATIO:
        recommended = CPU_FLOOR
        reasons.append("Disk pressure above 95%; recommend the floor and cleanup before more work.")
    if snapshot.load_average_1m is not None and snapshot.cpu_count:
        per_core = snapshot.load_average_1m / snapshot.cpu_count
        if per_core >= 1.0:
            recommended = max(CPU_FLOOR, recommended // 2)
            reasons.append(f"Load per core is {per_core:.2f}; halved the recommendation.")
        elif per_core <= 0.5:
            reasons.append(f"Load per core is {per_core:.2f}; capacity appears available.")
    if in_flight >= recommended:
        reasons.append(
            f"{in_flight} task(s) already in flight, at or above the recommendation of {recommended}."
        )
    if not reasons:
        reasons.append("No pressure signals detected.")
    return {
        "recommended_concurrency": recommended,
        "configured_max": configured_max,
        "in_flight": in_flight,
        "reasons": reasons,
        "applied_automatically": False,
        "note": "This endpoint is advisory and never changes a run. The orchestrator has a separate explicit opt-in adaptive cap.",
    }
