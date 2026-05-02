using System.Runtime.InteropServices;
using AgentShell.Listener.Events;

namespace AgentShell.Listener.Hooks;

/// <summary>
/// Low-level keyboard hook.
/// Aggregates keystrokes into bursts — emits one event per burst
/// instead of one per keystroke. Burst ends after BURST_GAP_MS idle.
/// </summary>
public sealed class KeyboardHook : IDisposable
{
    // ── Win32 ─────────────────────────────────────────────────────────────────
    private delegate IntPtr LowLevelKeyboardProc(int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(
        int idHook, LowLevelKeyboardProc lpfn, IntPtr hMod, uint dwThreadId);

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

    private const int WH_KEYBOARD_LL = 13;
    private const int WM_KEYDOWN     = 0x0100;
    private const int BURST_GAP_MS   = 1500;   // idle gap that ends a burst
    private const int MIN_BURST_CHARS = 3;      // ignore single keystrokes

    // ── State ─────────────────────────────────────────────────────────────────
    private readonly Action<AgentEvent> _emit;
    private readonly LowLevelKeyboardProc _proc;
    private readonly IntPtr _hook;

    private int    _burstCount;
    private string _burstWindow = "";
    private System.Threading.Timer? _flushTimer;
    private readonly object _lock = new();

    public KeyboardHook(Action<AgentEvent> emit)
    {
        _emit  = emit;
        _proc  = HookCallback;
        using var curProcess = System.Diagnostics.Process.GetCurrentProcess();
        using var curModule  = curProcess.MainModule!;
        _hook = SetWindowsHookEx(WH_KEYBOARD_LL, _proc,
            GetModuleHandle(curModule.ModuleName), 0);
    }

    private IntPtr HookCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode >= 0 && wParam == WM_KEYDOWN)
        {
            lock (_lock)
            {
                var window = GetActiveWindowTitle();

                // New burst or continuing burst in same window
                if (_burstWindow != window)
                {
                    FlushBurst();
                    _burstWindow = window;
                }

                _burstCount++;

                // Reset flush timer on each keystroke
                _flushTimer?.Dispose();
                _flushTimer = new System.Threading.Timer(
                    _ => FlushBurst(), null, BURST_GAP_MS, Timeout.Infinite);
            }
        }
        return CallNextHookEx(_hook, nCode, wParam, lParam);
    }

    private void FlushBurst()
    {
        lock (_lock)
        {
            if (_burstCount >= MIN_BURST_CHARS && !string.IsNullOrEmpty(_burstWindow))
            {
                _emit(AgentEvent.KeystrokeBurst(_burstWindow, _burstCount));
            }
            _burstCount  = 0;
            _burstWindow = "";
            _flushTimer?.Dispose();
            _flushTimer = null;
        }
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
        FlushBurst();
        if (_hook != IntPtr.Zero) UnhookWindowsHookEx(_hook);
        _flushTimer?.Dispose();
    }
}