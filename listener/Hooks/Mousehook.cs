using System.Runtime.InteropServices;
using AgentShell.Listener.Events;

namespace AgentShell.Listener.Hooks;

/// <summary>
/// Low-level mouse hook.
/// Only emits left-click events — ignores movement and scroll
/// to avoid flooding the pipe.
/// </summary>
public sealed class MouseHook : IDisposable
{
    // ── Win32 ─────────────────────────────────────────────────────────────────
    private delegate IntPtr LowLevelMouseProc(int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(
        int idHook, LowLevelMouseProc lpfn, IntPtr hMod, uint dwThreadId);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern bool UnhookWindowsHookEx(IntPtr hhk);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr CallNextHookEx(
        IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr GetModuleHandle(string? lpModuleName);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern int GetWindowText(
        IntPtr hwnd, System.Text.StringBuilder text, int count);

    [StructLayout(LayoutKind.Sequential)]
    private struct MSLLHOOKSTRUCT
    {
        public int     X;
        public int     Y;
        public uint    mouseData;
        public uint    flags;
        public uint    time;
        public IntPtr  dwExtraInfo;
    }

    private const int WH_MOUSE_LL    = 14;
    private const int WM_LBUTTONDOWN = 0x0201;
    private const int DEBOUNCE_MS    = 300;   // ignore double-fire within 300ms

    // ── State ─────────────────────────────────────────────────────────────────
    private readonly Action<AgentEvent>  _emit;
    private readonly LowLevelMouseProc   _proc;
    private readonly IntPtr              _hook;
    private long _lastClickMs;

    public MouseHook(Action<AgentEvent> emit)
    {
        _emit  = emit;
        _proc  = HookCallback;
        using var curProcess = System.Diagnostics.Process.GetCurrentProcess();
        using var curModule  = curProcess.MainModule!;
        _hook = SetWindowsHookEx(WH_MOUSE_LL, _proc,
            GetModuleHandle(curModule.ModuleName), 0);
    }

    private IntPtr HookCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode >= 0 && wParam == WM_LBUTTONDOWN)
        {
            var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            if (now - _lastClickMs > DEBOUNCE_MS)
            {
                _lastClickMs = now;
                var data     = Marshal.PtrToStructure<MSLLHOOKSTRUCT>(lParam);
                var window   = GetActiveWindowTitle();
                _emit(AgentEvent.Click(window, data.X, data.Y));
            }
        }
        return CallNextHookEx(_hook, nCode, wParam, lParam);
    }

    private static string GetActiveWindowTitle()
    {
        var hwnd = GetForegroundWindow();
        var sb   = new System.Text.StringBuilder(256);
        GetWindowText(hwnd, sb, sb.Capacity);
        return sb.ToString();
    }

    public void Dispose()
    {
        if (_hook != IntPtr.Zero) UnhookWindowsHookEx(_hook);
    }
}