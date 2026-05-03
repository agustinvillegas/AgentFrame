from agentshell import AgentShellClient
import anthropic

client = anthropic.Anthropic()
shell  = AgentShellClient()
schema = shell.schema()

messages = [
    {"role": "user", "content": f"Schema: {schema}\n\nTask: take a screenshot and tell me what's on screen"},
]

while True:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=f"You control a Windows PC via AgentShell.",
        messages=messages,
    )
    reply = response.content[0].text
    messages.append({"role": "assistant", "content": reply})

    import re
    commands = re.findall(r"```shell\n(.*?)\n```", reply, re.DOTALL)
    if not commands:
        print(reply)
        break

    for cmd in commands:
        result = shell.run(cmd.strip())
        messages.append({"role": "user", "content": f"Result: {result}"})