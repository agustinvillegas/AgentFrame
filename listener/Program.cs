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

        // Queue for thread-safe event passing to pipe writer
        var queue = new System.Collections.Concurrent.ConcurrentQueue<AgentEvent>();
        var signal = new SemaphoreSlim(0);

        void Emit(AgentEvent e)
        {
            queue.Enqueue(e);
            signal.Release();
        }

        // ── Start hooks ───────────────────────────────────────────────────────
        using var windowHook   = new WindowHook(Emit);
        using var keyboardHook = new KeyboardHook(Emit);
        using var mouseHook    = new MouseHook(Emit);
        using var clipboardWatcher = new ClipboardWatcher(Emit);
        
        Console.WriteLine("[Listener] Hooks active.");

        // ── Process watcher ───────────────────────────────────────────────────
        var (startWatcher, stopWatcher) = StartProcessWatcher(Emit);

        // ── Named pipe server loop ────────────────────────────────────────────
        var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

        Console.WriteLine($"[Listener] Waiting for client on pipe '{PIPE_NAME}'...");

        
        var heartbeatPath = Path.Combine(
            AppContext.BaseDirectory, "..", "..", "..", "..", "..", 
            "data", "listener_heartbeat.json");

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
                    version = "0.4",
                });
                await File.WriteAllTextAsync(heartbeatPath, payload, cts.Token);
            }
            catch { /* nunca romper el listener por un heartbeat fallido */ }

            await Task.Delay(5000, cts.Token);
        }
    }, cts.Token);

            while (!cts.Token.IsCancellationRequested)
            {
                try
                {
                await using var pipe = new NamedPipeServerStream(
                    PIPE_NAME,
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
                        try
                        {
                            await writer.WriteLineAsync(evt.ToJson());
                        }
                        catch
                        {
                            break;
                        }
                    }
                }

                Console.WriteLine("[Listener] Client disconnected. Waiting for next...");
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[Listener] Pipe error: {ex.Message}. Restarting...");
                await Task.Delay(500, cts.Token);
            }
        }

        processWatcher?.Dispose();
        startWatcher?.Dispose();
        stopWatcher.Dispose();
        Console.WriteLine("[Listener] Stopped.");
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