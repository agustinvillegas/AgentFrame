from agentshell import AgentShellClient
from openai import OpenAI

client = OpenAI()
shell  = AgentShellClient()
schema = shell.schema()

messages = [
    {"role": "system", "content": f"You control a Windows PC via AgentShell. Schema: {schema}"},
    {"role": "user",   "content": "Task: open Notepad and type Hello World"},
]

while True:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )
    reply = response.choices[0].message.content
    messages.append({"role": "assistant", "content": reply})

    import re
    commands = re.findall(r"```shell\n(.*?)\n```", reply, re.DOTALL)
    if not commands:
        print(reply)
        break

    for cmd in commands:
        result = shell.run(cmd.strip())
        messages.append({"role": "user", "content": f"Result: {result}"})