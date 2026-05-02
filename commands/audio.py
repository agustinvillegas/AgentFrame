from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam
import pyaudio


@registry.register(
    group="audio",
    name="volume",
    description="Get or set system volume.",
    params=[
        CommandParam("set", "int", False, None, "Set volume to this level (0-100). Omit to get current volume."),
    ]
)
def volume(set: int | None = None) -> AgentResponse:
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        import math

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))

        if set is not None:
            level = max(0, min(100, set))
            db = -65.25 if level == 0 else max(-65.25, 20 * math.log10(level / 100))
            vol.SetMasterVolumeLevel(db, None)
            return AgentResponse.success(
                {"volume": level},
                state_delta={"volume": level}
            )
        else:
            current_db = vol.GetMasterVolumeLevel()
            current_pct = 0 if current_db <= -65.25 else round(10 ** (current_db / 20) * 100)
            muted = bool(vol.GetMute())
            return AgentResponse.success({"volume": current_pct, "muted": muted})

    except ImportError:
        return AgentResponse.failure("pycaw not installed. Run: pip install pycaw comtypes")
    except Exception as e:
        return AgentResponse.failure(f"Volume operation failed: {e}")


@registry.register(
    group="audio",
    name="mute",
    description="Mute or unmute system audio.",
    params=[
        CommandParam("state", "bool", False, None, "True to mute, False to unmute. Omit to toggle."),
    ]
)
def mute(state: bool | None = None) -> AgentResponse:
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))

        if state is None:
            state = not bool(vol.GetMute())

        vol.SetMute(int(state), None)
        return AgentResponse.success(
            {"muted": state},
            state_delta={"muted": state}
        )
    except ImportError:
        return AgentResponse.failure("pycaw not installed. Run: pip install pycaw comtypes")
    except Exception as e:
        return AgentResponse.failure(f"Mute operation failed: {e}")


@registry.register(
    group="audio",
    name="devices",
    description="List available audio devices. Use --type to filter by input or output.",
    params=[
        CommandParam("type", "string", False, "output", "'output' for speakers/headphones, 'input' for microphones"),
    ]
)
def devices(type: str = "output") -> AgentResponse:
    try:
        import pyaudio

        pa        = pyaudio.PyAudio()
        count     = pa.get_device_count()
        result    = []
        host_type = "output" if type == "output" else "input"

        for i in range(count):
            try:
                info = pa.get_device_info_by_index(i)
                # Filtrar por tipo
                if host_type == "output" and info.get("maxOutputChannels", 0) == 0:
                    continue
                if host_type == "input" and info.get("maxInputChannels", 0) == 0:
                    continue

                result.append({
                    "index": i,
                    "name":  info.get("name", f"Device {i}"),
                    "channels": info.get("maxOutputChannels") if host_type == "output" else info.get("maxInputChannels"),
                    "default_sr": int(info.get("defaultSampleRate", 0)),
                })
            except Exception:
                continue

        pa.terminate()

        return AgentResponse.success({
            "devices": result,
            "count":   len(result),
            "type":    type,
        })

    except ImportError:
        return AgentResponse.failure("pyaudio not installed. Run: pip install pyaudio")
    except Exception as e:
        return AgentResponse.failure(f"Device enumeration failed: {e}")


@registry.register(
    group="audio",
    name="device",
    description="Set the default audio device by index or name fragment.",
    params=[
        CommandParam("name",  "string", False, None, "Partial device name to match"),
        CommandParam("index", "int",    False, None, "Device index from 'audio devices'"),
        CommandParam("type",  "string", False, "output", "'output' or 'input'"),
    ]
)
def device(name: str | None = None, index: int | None = None, type: str = "output") -> AgentResponse:
    try:
        from pycaw.pycaw import AudioUtilities
        sessions = AudioUtilities.GetAllSessions()
        # Obtener nombre via propiedades del dispositivo
        name = device.GetId()
        props = device.OpenPropertyStore(0)
        val = props.GetValue(
            "{a45c254e-df1c-4efd-8020-67d146a850e0}",
            14
        )
        name = str(val.GetValue())
    except Exception:
        # Fallback: intentar via pyaudio
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            info = pa.get_device_info_by_index(i)
            name = info.get("name", f"Device {i}")
            pa.terminate()
        except Exception:
            name = f"Device {i}"
    
    
@registry.register(
    group="audio",
    name="app",
    description="Get or set volume/mute for a specific app, or list all apps with active audio.",
    params=[
        CommandParam("name",  "string", False, None,  "Process name to target (e.g. 'chrome.exe'). Omit to list all."),
        CommandParam("set",   "int",    False, None,  "Set volume (0-100) for the target app."),
        CommandParam("mute",  "bool",   False, None,  "True to mute, False to unmute. Omit to toggle."),
    ]
)
def app_audio(name: str | None = None, set: int | None = None, mute: bool | None = None) -> AgentResponse:
    try:
        from pycaw.pycaw import AudioUtilities

        sessions = AudioUtilities.GetAllSessions()

        # Sin nombre → listar todas las apps con audio activo
        if name is None:
            apps = []
            for s in sessions:
                if s.Process:
                    vol   = s.SimpleAudioVolume
                    level = round(vol.GetMasterVolume() * 100)
                    apps.append({
                        "name":   s.Process.name(),
                        "pid":    s.Process.pid,
                        "volume": level,
                        "muted":  bool(vol.GetMute()),
                    })
            return AgentResponse.success({"apps": apps, "count": len(apps)})

        # Con nombre → buscar la sesión
        target = None
        for s in sessions:
            if s.Process and name.lower() in s.Process.name().lower():
                target = s
                break

        if not target:
            return AgentResponse.failure(f"No active audio session found for '{name}'.")

        vol       = target.SimpleAudioVolume
        proc_name = target.Process.name()

        if set is not None:
            level = max(0, min(100, set))
            vol.SetMasterVolume(level / 100, None)
            return AgentResponse.success(
                {"app": proc_name, "volume": level},
                state_delta={"last_action": f"set {proc_name} volume to {level}", "result": f"{proc_name} volume is {level}"}
            )

        if mute is not None:
            vol.SetMute(int(mute), None)
            state = "muted" if mute else "unmuted"
            return AgentResponse.success(
                {"app": proc_name, "muted": mute},
                state_delta={"last_action": f"{state} {proc_name}", "result": f"{proc_name} is {state}"}
            )

        # Sin set ni mute → get estado actual
        current = round(vol.GetMasterVolume() * 100)
        return AgentResponse.success({
            "app":    proc_name,
            "volume": current,
            "muted":  bool(vol.GetMute()),
        })

    except ImportError:
        return AgentResponse.failure("pycaw not installed. Run: pip install pycaw")
    except Exception as e:
        return AgentResponse.failure(f"App audio operation failed: {e}")