from __future__ import annotations
from core.response import AgentResponse
from core.registry import registry, CommandParam


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
        from pycaw.pycaw import AudioUtilities, EDataFlow, ERole
        from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
        from comtypes import CLSCTX_ALL
        import comtypes.client

        enumerator = comtypes.client.CreateObject(
            "{BCDE0395-E52F-467C-8E3D-C4579291692E}",
            interface=IMMDeviceEnumerator
        )

        flow = EDataFlow.eRender if type == "output" else EDataFlow.eCapture
        collection = enumerator.EnumAudioEndpoints(flow, 1)  # 1 = DEVICE_STATE_ACTIVE
        count = collection.GetCount()

        result = []
        for i in range(count):
            device = collection.Item(i)
            dev_id = device.GetId()
            props  = device.OpenPropertyStore(0)  # STGM_READ

            try:
                name = props.GetValue(
                    "{a45c254e-df1c-4efd-8020-67d146a850e0}", 14  # PKEY_Device_FriendlyName
                ).GetValue()
            except Exception:
                name = f"Device {i}"

            result.append({
                "index": i,
                "id":    dev_id,
                "name":  name,
            })

        return AgentResponse.success({
            "devices": result,
            "count":   len(result),
            "type":    type,
        })

    except ImportError:
        return AgentResponse.failure("pycaw not installed. Run: pip install pycaw comtypes")
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
        import subprocess
        if name is None and index is None:
            return AgentResponse.failure("Provide --name or --index.")

        if name:
            script = f"""
            $device = Get-AudioDevice -List | Where-Object {{ $_.Type -eq '{type.capitalize()}' -and $_.Name -like '*{name}*' }} | Select-Object -First 1
            if ($device) {{ Set-AudioDevice -Id $device.Id; Write-Output $device.Name }}
            else {{ Write-Error 'Device not found' }}
            """
        else:
            script = f"""
            $device = (Get-AudioDevice -List | Where-Object {{ $_.Type -eq '{type.capitalize()}' }})[$index]
            if ($device) {{ Set-AudioDevice -Id $device.Id; Write-Output $device.Name }}
            else {{ Write-Error 'Device not found' }}
            """

        result = subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0 or result.stderr:
            return AgentResponse.failure(
                f"Could not set device. Ensure 'AudioDeviceCmdlets' is installed: "
                f"Install-Module -Name AudioDeviceCmdlets"
            )

        set_name = result.stdout.strip()
        return AgentResponse.success(
            {"set": set_name, "type": type},
            state_delta={"last_action": f"changed {type} device to {set_name}", "result": f"{type} device changed"}
        )

    except subprocess.TimeoutExpired:
        return AgentResponse.failure("PowerShell timeout.")
    except Exception as e:
        return AgentResponse.failure(f"Device switch failed: {e}")
    
    
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