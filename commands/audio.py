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
