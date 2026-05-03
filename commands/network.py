from __future__ import annotations
import psutil
import socket
from core.response import AgentResponse
from core.registry import registry, CommandParam


@registry.register(
    group="network",
    name="status",
    description="Get current network connection status and local IP addresses.",
    params=[]
)
def status() -> AgentResponse:
    try:
        # Verificar conectividad
        connected = False
        try:
            socket.setdefaulttimeout(3)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            connected = True
        except Exception:
            pass

        # IPs locales por interfaz
        interfaces = []
        for name, addrs in psutil.net_if_addrs().items():
            ips = []
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ips.append(addr.address)
            if ips:
                stats = psutil.net_if_stats().get(name)
                interfaces.append({
                    "name":    name,
                    "ips":     ips,
                    "up":      stats.isup if stats else None,
                    "speed_mb": stats.speed if stats else None,
                })

        return AgentResponse.success({
            "connected":  connected,
            "interfaces": interfaces,
        })
    except Exception as e:
        return AgentResponse.failure(f"Network status failed: {e}")


@registry.register(
    group="network",
    name="ip",
    description="Get public IP address.",
    params=[]
)
def ip() -> AgentResponse:
    try:
        import urllib.request
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as r:
            public_ip = r.read().decode().strip()

        local_ip = socket.gethostbyname(socket.gethostname())

        return AgentResponse.success({
            "public":  public_ip,
            "local":   local_ip,
        })
    except Exception as e:
        return AgentResponse.failure(f"IP query failed: {e}")


@registry.register(
    group="network",
    name="connections",
    description="List active network connections. Optionally filter by process name.",
    params=[
        CommandParam("filter", "string", False, None, "Filter by process name (e.g. 'brave.exe')"),
    ]
)
def connections(filter: str | None = None) -> AgentResponse:
    try:
        result = []
        filter_lower = filter.lower().replace(".exe", "") if filter else None

        for conn in psutil.net_connections(kind="inet"):
            try:
                proc_name = None
                if conn.pid:
                    try:
                        proc_name = psutil.Process(conn.pid).name()
                    except Exception:
                        pass

                if filter_lower and proc_name:
                    if filter_lower not in proc_name.lower():
                        continue

                laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None
                raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None

                result.append({
                    "pid":     conn.pid,
                    "process": proc_name,
                    "local":   laddr,
                    "remote":  raddr,
                    "status":  conn.status,
                })
            except Exception:
                continue

        return AgentResponse.success({
            "connections": result,
            "count":       len(result),
        })
    except Exception as e:
        return AgentResponse.failure(f"Connections query failed: {e}")