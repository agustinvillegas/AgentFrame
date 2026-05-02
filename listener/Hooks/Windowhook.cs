using System.Runtime.InteropServices;
using System.Text;
using AgentShell.Listener.Events;

namespace AgentShell.Listener.Hooks;

public sealed class WindowHook : IDisposable
{
    // ── Win32 ─────────────────────────────────────────────────────────────────
    private delegate void WinEventProc(
        IntPtr hWinEventHook, uint eventType, IntPtr hwnd,
        int idObject, int idChild, uint dwEventThread, uint dwmsEventTime);

    [DllImport("user32.dll")]
    private static extern IntPtr SetWinEventHook(
        uint eventMin, uint eventMax, IntPtr hmodWinEventProc,
        WinEventProc lpfnWinEventProc, uint idProcess, uint idThread, uint dwFlags);

    [DllImport("user32.dll")]
    private static extern bool UnhookWinEvent(IntPtr hWinEventHook);

    [DllImport("user32.dll")]
    private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);

    [DllImport("user32.dll")]
    private static extern int GetWindowTextLength(IntPtr hwnd);

    private const uint EVENT_SYSTEM_FOREGROUND = 0x0003;
    private const uint EVENT_OBJECT_NAMECHANGE  = 0x800C;
    private const uint WINEVENT_OUTOFCONTEXT    = 0x0000;

    // ── State ─────────────────────────────────────────────────────────────────
    private readonly Action<AgentEvent> _emit;
    private readonly WinEventProc       _proc;  // keep ref to prevent GC
    private readonly IntPtr             _hookFg;
    private readonly IntPtr             _hookName;
    private string _lastWindow = "";

    private static readonly HashSet<string> _browserProcesses =
        new(StringComparer.OrdinalIgnoreCase)
        { "chrome", "firefox", "msedge", "opera", "brave" };

    public WindowHook(Action<AgentEvent> emit)
    {
        _emit      = emit;
        _proc      = OnWinEvent;
        _hookFg    = SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
            IntPtr.Zero, _proc, 0, 0, WINEVENT_OUTOFCONTEXT);
        _hookName  = SetWinEventHook(
            EVENT_OBJECT_NAMECHANGE, EVENT_OBJECT_NAMECHANGE,
            IntPtr.Zero, _proc, 0, 0, WINEVENT_OUTOFCONTEXT);
    }

    private void OnWinEvent(
        IntPtr hWinEventHook, uint eventType, IntPtr hwnd,
        int idObject, int idChild, uint dwEventThread, uint dwmsEventTime)
    {
        var title = GetTitle(hwnd);
        if (string.IsNullOrWhiteSpace(title)) return;

        if (eventType == EVENT_SYSTEM_FOREGROUND)
        {
            if (title == _lastWindow) return;
            _lastWindow = title;
            _emit(AgentEvent.WindowChange(title));
        }
        else if (eventType == EVENT_OBJECT_NAMECHANGE)
        {
            // Only fire tab changes for browser windows
            var procName = GetProcessName(hwnd);
            if (!_browserProcesses.Contains(procName)) return;
            if (title == _lastWindow) return;
            _lastWindow = title;
            _emit(AgentEvent.TabChange(title));
        }
    }

    private static string GetTitle(IntPtr hwnd)
    {
        int len = GetWindowTextLength(hwnd);
        if (len == 0) return "";
        var sb = new StringBuilder(len + 1);
        GetWindowText(hwnd, sb, sb.Capacity);
        return sb.ToString();
    }

    private static string GetProcessName(IntPtr hwnd)
    {
        try
        {
            _ = GetWindowThreadProcessId(hwnd, out uint pid);
            var proc = System.Diagnostics.Process.GetProcessById((int)pid);
            return proc.ProcessName;
        }
        catch { return ""; }
    }

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);

    public void Dispose()
    {
        if (_hookFg   != IntPtr.Zero) UnhookWinEvent(_hookFg);
        if (_hookName != IntPtr.Zero) UnhookWinEvent(_hookName);
    }
}