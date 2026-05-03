from agentshell import AgentShellClient
from groq import Groq

SYSTEM_PROMPT = """You control a Windows PC via AgentShell.
Call shell.run(command) to execute commands.
Every command returns JSON with ok, data, and optionally error.
Start by calling help --json to get the full command schema.
Always check context get to know the current state before acting."""

client = Groq()
shell  = AgentShellClient()
schema = shell.schema()

messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user",   "content": f"Available commands:\n{schema}\n\nTask: list all open windows"},
]

while True:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
    )
    reply = response.choices[0].message.content
    messages.append({"role": "assistant", "content": reply})

    # El agente escribe comandos entre triple backticks
    import re
    commands = re.findall(r"```shell\n(.*?)\n```", reply, re.DOTALL)
    if not commands:
        print(reply)
        break

    for cmd in commands:
        result = shell.run(cmd.strip())
        messages.append({"role": "user", "content": f"Result: {result}"})