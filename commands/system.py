from __future__ import annotations
import psutil
import datetime
from core.response import AgentResponse
from core.registry import registry, CommandParam


@registry.register(
    group="system",
    name="info",
    description="Get general system information: OS, CPU, RAM, uptime, current time.",
    params=[]
)
def info() -> AgentResponse:
    try:
        import platform

        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime_s  = int((datetime.datetime.now() - boot_time).total_seconds())

        mem  = psutil.virtual_memory()
        cpu  = psutil.cpu_percent(interval=0.5)

        return AgentResponse.success({
            "os":         platform.system() + " " + platform.version(),
            "cpu_percent": cpu,
            "ram": {
                "total_mb":     mem.total     // (1024 * 1024),
                "available_mb": mem.available // (1024 * 1024),
                "used_percent": mem.percent,
            },
            "uptime_seconds": uptime_s,
            "time":           datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    except Exception as e:
        return AgentResponse.failure(f"System info failed: {e}")


@registry.register(
    group="system",
    name="battery",
    description="Get battery status. Returns null if no battery (desktop PC).",
    params=[]
)
def battery() -> AgentResponse:
    try:
        bat = psutil.sensors_battery()
        if bat is None:
            return AgentResponse.success({
                "battery": None,
                "note":    "No battery detected — likely a desktop PC.",
            })

        return AgentResponse.success({
            "percent":    round(bat.percent, 1),
            "plugged_in": bat.power_plugged,
            "seconds_left": bat.secsleft if bat.secsleft != psutil.POWER_TIME_UNLIMITED else None,
        })
    except Exception as e:
        return AgentResponse.failure(f"Battery query failed: {e}")


@registry.register(
    group="system",
    name="cpu",
    description="Get per-core CPU usage.",
    params=[
        CommandParam("interval", "float", False, 0.5, "Measurement interval in seconds. Higher = more accurate."),
    ]
)
def cpu(interval: float = 0.5) -> AgentResponse:
    try:
        per_core = psutil.cpu_percent(interval=interval, percpu=True)
        total    = psutil.cpu_percent(interval=0)

        return AgentResponse.success({
            "total_percent": total,
            "cores":         len(per_core),
            "per_core":      per_core,
        })
    except Exception as e:
        return AgentResponse.failure(f"CPU query failed: {e}")


@registry.register(
    group="system",
    name="ram",
    description="Get detailed RAM usage.",
    params=[]
)
def ram() -> AgentResponse:
    try:
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return AgentResponse.success({
            "ram": {
                "total_mb":     mem.total     // (1024 * 1024),
                "available_mb": mem.available // (1024 * 1024),
                "used_mb":      mem.used      // (1024 * 1024),
                "used_percent": mem.percent,
            },
            "swap": {
                "total_mb": swap.total // (1024 * 1024),
                "used_mb":  swap.used  // (1024 * 1024),
                "percent":  swap.percent,
            },
        })
    except Exception as e:
        return AgentResponse.failure(f"RAM query failed: {e}")


@registry.register(
    group="system",
    name="disk",
    description="Get disk usage for all mounted drives.",
    params=[]
)
def disk() -> AgentResponse:
    try:
        partitions = psutil.disk_partitions()
        result     = []

        for p in partitions:
            try:
                usage = psutil.disk_usage(p.mountpoint)
                result.append({
                    "drive":      p.mountpoint,
                    "filesystem": p.fstype,
                    "total_gb":   round(usage.total / (1024 ** 3), 1),
                    "used_gb":    round(usage.used  / (1024 ** 3), 1),
                    "free_gb":    round(usage.free  / (1024 ** 3), 1),
                    "percent":    usage.percent,
                })
            except Exception:
                continue

        return AgentResponse.success({"drives": result, "count": len(result)})
    except Exception as e:
        return AgentResponse.failure(f"Disk query failed: {e}")