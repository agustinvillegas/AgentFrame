using System.IO.Pipes;
using System.Management;
using AgentShell.Listener.Events;
using AgentShell.Listener.Hooks;

namespace AgentShell.Listener;

class Program
{
    private const string PIPE_NAME = "agentshell_listener";

    static async Task Main(string[] args)
{
    Console.WriteLine("[Listener] Starting AgentShell Listener...");

    var queue  = new System.Collections.Concurrent.ConcurrentQueue<AgentEvent>();
    var signal = new SemaphoreSlim(0);

    void Emit(AgentEvent e)
    {
        queue.Enqueue(e);
        signal.Release();
    }

    // ── Hooks en thread dedicado con message loop propio ──────────────────
    var hooksReady = new TaskCompletionSource();
    var hookThread = new Thread(() =>
    {
        using var windowHook   = new WindowHook(Emit);
        using var keyboardHook = new KeyboardHook(Emit);
        using var mouseHook    = new MouseHook(Emit);

        Console.WriteLine("[Listener] Hooks active.");
        hooksReady.SetResult();

        // Message loop dedicado para los hooks
        var msg = new MSG();
        while (GetMessage(ref msg, IntPtr.Zero, 0, 0))
        {
            TranslateMessage(ref msg);
            DispatchMessage(ref msg);
        }
    });
    hookThread.SetApartmentState(ApartmentState.STA);
    hookThread.IsBackground = true;
    hookThread.Start();

    await hooksReady.Task;

    // ── Process watcher ───────────────────────────────────────────────────
    var (startWatcher, stopWatcher) = StartProcessWatcher(Emit);

    
    var cts = new CancellationTokenSource();
    Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

    var heartbeatPath = Path.Combine(FindDataDir(), "listener_heartbeat.json");
    Console.WriteLine($"[Listener] Heartbeat path: {heartbeatPath}");

    _ = Task.Run(async () =>    
    {
        while (!cts.Token.IsCancellationRequested)
        {
            try
            {
                var dir = Path.GetDirectoryName(heartbeatPath)!;
                Directory.CreateDirectory(dir);
                var payload = System.Text.Json.JsonSerializer.Serialize(new
                {
                    ts      = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
                    status  = "running",
                    version = "1.1",
                });
                await File.WriteAllTextAsync(heartbeatPath, payload, cts.Token);
            }
            catch { }
            await Task.Delay(5000, cts.Token);
        }
    }, cts.Token);

    // ── Named pipe server loop ────────────────────────────────────────────
    Console.WriteLine($"[Listener] Waiting for client on pipe...");

    while (!cts.Token.IsCancellationRequested)
    {
        try
        {
            await using var pipe = new NamedPipeServerStream(
                "agentshell_listener",
                PipeDirection.Out,
                1,
                PipeTransmissionMode.Byte,
                PipeOptions.Asynchronous);

            await pipe.WaitForConnectionAsync(cts.Token);
            Console.WriteLine("[Listener] Client connected.");

            using var writer = new StreamWriter(pipe) { AutoFlush = true };

            while (pipe.IsConnected && !cts.Token.IsCancellationRequested)
            {
                await signal.WaitAsync(cts.Token);
                while (queue.TryDequeue(out var evt))
                {
                    try { await writer.WriteLineAsync(evt.ToJson()); }
                    catch { break; }
                }
            }

            Console.WriteLine("[Listener] Client disconnected.");
        }
        catch (OperationCanceledException) { break; }
        catch (Exception ex)
        {
            Console.WriteLine($"[Listener] Pipe error: {ex.Message}. Restarting...");
            await Task.Delay(500, cts.Token);
        }
    }

    startWatcher?.Dispose();
    stopWatcher?.Dispose();
    Console.WriteLine("[Listener] Stopped.");
}

// ── Win32 message loop ────────────────────────────────────────────────────
[System.Runtime.InteropServices.DllImport("user32.dll")]
private static extern bool GetMessage(ref MSG msg, IntPtr hwnd, uint min, uint max);

[System.Runtime.InteropServices.DllImport("user32.dll")]
private static extern bool TranslateMessage(ref MSG msg);

[System.Runtime.InteropServices.DllImport("user32.dll")]
private static extern IntPtr DispatchMessage(ref MSG msg);

[System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
private struct MSG
{
    public IntPtr hwnd;
    public uint   message;
    public IntPtr wParam;
    public IntPtr lParam;
    public uint   time;
    public int    ptX, ptY;
}

private static string FindDataDir()
{
    var dir = new DirectoryInfo(AppContext.BaseDirectory);
    while (dir != null)
    {
        var candidate = Path.Combine(dir.FullName, "data");
        // Verificar que es la carpeta data correcta — tiene memory.db
        if (Directory.Exists(candidate) && File.Exists(Path.Combine(candidate, "memory.db")))
            return candidate;
        dir = dir.Parent;
    }
    var fallback = Path.Combine(AppContext.BaseDirectory, "data");
    Directory.CreateDirectory(fallback);
    return fallback;
}
   // La función cambia su retorno:
private static (ManagementEventWatcher?, ManagementEventWatcher?) StartProcessWatcher(Action<AgentEvent> emit)
{
    try
    {
        var startQuery = new WqlEventQuery("SELECT * FROM Win32_ProcessStartTrace");
        var startWatcher = new ManagementEventWatcher(startQuery);
        startWatcher.EventArrived += (_, e) =>
        {
            var name = e.NewEvent["ProcessName"]?.ToString() ?? "";
            var pid  = Convert.ToInt32(e.NewEvent["ProcessID"]);
            if (!string.IsNullOrEmpty(name))
                emit(AgentEvent.ProcessStart(name, pid));
        };
        startWatcher.Start();

        var stopQuery = new WqlEventQuery("SELECT * FROM Win32_ProcessStopTrace");
        var stopWatcher = new ManagementEventWatcher(stopQuery);
        stopWatcher.EventArrived += (_, e) =>
        {
            var name = e.NewEvent["ProcessName"]?.ToString() ?? "";
            var pid  = Convert.ToInt32(e.NewEvent["ProcessID"]);
            if (!string.IsNullOrEmpty(name))
                emit(AgentEvent.ProcessStop(name, pid));
        };
        stopWatcher.Start();

        Console.WriteLine("[Listener] Process watcher active.");
        return (startWatcher, stopWatcher);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"[Listener] Process watcher unavailable: {ex.Message}");
        return (null, null);
    }
}
}