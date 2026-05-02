using System.Text.Json;
using System.Text.Json.Serialization;

namespace AgentShell.Listener.Events;

public enum EventType
{
    window_change,
    tab_change,
    process_start,
    process_stop,
    keystroke_burst,
    click,
    clipboard_change,
}

public sealed class AgentEvent
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "";

    [JsonPropertyName("window")]
    public string? Window { get; init; }

    [JsonPropertyName("name")]
    public string? Name { get; init; }

    [JsonPropertyName("pid")]
    public int? Pid { get; init; }

    [JsonPropertyName("x")]
    public int? X { get; init; }

    [JsonPropertyName("y")]
    public int? Y { get; init; }

    [JsonPropertyName("char_count")]
    public int? CharCount { get; init; }

    [JsonPropertyName("ts")]
    public long Ts { get; init; } = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

    // ── Factories ─────────────────────────────────────────────────────────────

    public static AgentEvent WindowChange(string window) => new()
    {
        Type   = nameof(EventType.window_change),
        Window = window,
    };
    public static AgentEvent ClipboardChange(string preview, int length) => new()
{
    Type    = nameof(EventType.clipboard_change),
    Window  = preview.Length > 120 ? preview[..120] + "..." : preview,
    CharCount = length,
};

    public static AgentEvent TabChange(string window) => new()
    {
        Type   = nameof(EventType.tab_change),
        Window = window,
    };

    public static AgentEvent ProcessStart(string name, int pid) => new()
    {
        Type = nameof(EventType.process_start),
        Name = name,
        Pid  = pid,
    };

    public static AgentEvent ProcessStop(string name, int pid) => new()
    {
        Type = nameof(EventType.process_stop),
        Name = name,
        Pid  = pid,
    };

    public static AgentEvent KeystrokeBurst(string window, int charCount) => new()
    {
        Type      = nameof(EventType.keystroke_burst),
        Window    = window,
        CharCount = charCount,
    };

    public static AgentEvent Click(string window, int x, int y) => new()
    {
        Type   = nameof(EventType.click),
        Window = window,
        X      = x,
        Y      = y,
    };

    public string ToJson() =>
        JsonSerializer.Serialize(this, new JsonSerializerOptions
        {
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        });
}