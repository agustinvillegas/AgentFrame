using System.Runtime.InteropServices;
using AgentShell.Listener.Events;

namespace AgentShell.Listener.Hooks;

public sealed class ClipboardWatcher : IDisposable
{
    [DllImport("user32.dll")] private static extern bool AddClipboardFormatListener(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool RemoveClipboardFormatListener(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern IntPtr GetClipboardOwner();
    [DllImport("user32.dll")] private static extern bool OpenClipboard(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool CloseClipboard();
    [DllImport("user32.dll")] private static extern bool IsClipboardFormatAvailable(uint format);
    [DllImport("user32.dll")] private static extern IntPtr GetClipboardData(uint format);
    [DllImport("kernel32.dll")] private static extern IntPtr GlobalLock(IntPtr hMem);
    [DllImport("kernel32.dll")] private static extern bool GlobalUnlock(IntPtr hMem);

    private const uint CF_UNICODETEXT  = 13;
    private const int  WM_CLIPBOARDUPDATE = 0x031D;
    private const int  MAX_PREVIEW_CHARS  = 120;

    private readonly Action<AgentEvent> _emit;
    private readonly Thread             _thread;
    private IntPtr                      _hwnd;
    private bool                        _running = true;

    public ClipboardWatcher(Action<AgentEvent> emit)
    {
        _emit   = emit;
        _thread = new Thread(MessageLoop) { IsBackground = true };
        _thread.SetApartmentState(ApartmentState.STA); // requerido para clipboard
        _thread.Start();
    }

    private void MessageLoop()
    {
        // Crear ventana oculta
        _hwnd = CreateMessageWindow();
        if (_hwnd == IntPtr.Zero) return;

        AddClipboardFormatListener(_hwnd);

        var msg = new MSG();
        while (_running && GetMessage(ref msg, IntPtr.Zero, 0, 0))
        {
            if (msg.message == WM_CLIPBOARDUPDATE)
            {
                var text = ReadClipboardText();
                if (!string.IsNullOrEmpty(text))
                    _emit(AgentEvent.ClipboardChange(text, text.Length));
            }
            TranslateMessage(ref msg);
            DispatchMessage(ref msg);
        }

        RemoveClipboardFormatListener(_hwnd);
        DestroyWindow(_hwnd);
    }

    private static string? ReadClipboardText()
    {
        if (!IsClipboardFormatAvailable(CF_UNICODETEXT)) return null;
        if (!OpenClipboard(IntPtr.Zero)) return null;
        try
        {
            var handle = GetClipboardData(CF_UNICODETEXT);
            if (handle == IntPtr.Zero) return null;
            var ptr = GlobalLock(handle);
            if (ptr == IntPtr.Zero) return null;
            try { return Marshal.PtrToStringUni(ptr); }
            finally { GlobalUnlock(handle); }
        }
        finally { CloseClipboard(); }
    }

    // ── Win32 message loop ────────────────────────────────────────────────────
    [DllImport("user32.dll")] private static extern bool GetMessage(ref MSG msg, IntPtr hwnd, uint min, uint max);
    [DllImport("user32.dll")] private static extern bool TranslateMessage(ref MSG msg);
    [DllImport("user32.dll")] private static extern IntPtr DispatchMessage(ref MSG msg);
    [DllImport("user32.dll")] private static extern bool DestroyWindow(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern void PostQuitMessage(int code);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr CreateWindowEx(
        uint dwExStyle, string lpClassName, string lpWindowName,
        uint dwStyle, int x, int y, int w, int h,
        IntPtr hWndParent, IntPtr hMenu, IntPtr hInstance, IntPtr lpParam);

    private static IntPtr CreateMessageWindow()
    {
        return CreateWindowEx(0, "STATIC", "AgentShellClipboard",
            0, 0, 0, 0, 0,
            new IntPtr(-3), // HWND_MESSAGE
            IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MSG
    {
        public IntPtr hwnd;
        public uint   message;
        public IntPtr wParam;
        public IntPtr lParam;
        public uint   time;
        public int    ptX, ptY;
    }

    public void Dispose()
    {
        _running = false;
        PostQuitMessage(0);
    }
}