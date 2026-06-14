import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

MODEL = "openrouter/free"

SYSTEM_PROMPT = """You are a helpful file assistant with access to the following tools:

- read_file(path: str): reads a file from disk and returns its content
- write_file(path: str, content: str): writes content to a file on disk

When you need to use a tool, emit EXACTLY this format:

<tool_call>
{"name": "read_file", "arguments": {"path": "example.txt"}}
</tool_call>

After you receive the tool result in a <tool_response> block, continue your response."""

def read_file(path: str) -> dict:
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: {path} file not found"
def write_file(path, content):
    try: 
        with open(path, "w") as f:
            f.write(content)
        return f"Successfully written to {path}"
    except OSError as e:
        return f"Error: {e}"

def parse_tool_call(response_text):
    try:
        match = re.search(r"<tool_call>(.*?)</tool_call>" , response_text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            return data["name"] , data["arguments"]
        return None, None
    except (json.JSONDecodeError, KeyError):
        return None, None

def dispatch_text(name, arguments):
    try:
        if name == "read_file":
            result = read_file(arguments["path"])
        elif name == "write_file":
            result = write_file(arguments["path"], arguments["content"])
        else:
            result = f"unknown file: {name}"
        return json.dumps({"results ": result})
    except KeyError as e:
        return json.dumps({"error": f"Missing argument: {e}"})
    
def run_agent(user_message):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]

    for i in range(10):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages
            )
            response_text = response.choices[0].message.content
        except Exception as e:
            print(f"API error: {e}")
            break

        name, arguments = parse_tool_call(response_text)

        if name is None:
            print("\nAgent:", response_text)
            break

        print(f"\n[Tool call: {name}({arguments})]")
        tool_result = dispatch_text(name, arguments)
        print(f"[Tool result: {tool_result}]")

        messages.append({"role": "assistant", "content": response_text})
        messages.append({"role": "user", "content": f"<tool_response>{tool_result}</tool_response>"})

# ---- Run ----
if __name__ == "__main__":
    run_agent("Read the file sample.txt and summarise what's in it")
    