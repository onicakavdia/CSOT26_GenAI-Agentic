


import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


THIS_FOLDER = Path(__file__).parent.resolve()
TARGET_REPO = THIS_FOLDER / "target_repo"          
SESSIONS_FOLDER = THIS_FOLDER / "sessions"          
MODEL_NAME = "openrouter/free"
MAX_STEPS = 40           
COMMAND_TIMEOUT = 30     


def now():
    """Just a short helper to get the current time as text."""
    return datetime.now(timezone.utc).isoformat()



def make_demo_repo_if_missing():
    """
    If target_repo/ does not exist yet, create a tiny demo project with
    one real bug in it. This means you can run the agent immediately
    without having to go find and download a real codebase first.
    """
    if TARGET_REPO.exists():
        return  

    print(f"No target_repo/ found - creating a small demo project at {TARGET_REPO}")

    src_folder = TARGET_REPO / "src"
    tests_folder = TARGET_REPO / "tests"
    src_folder.mkdir(parents=True)
    tests_folder.mkdir(parents=True)

    
    auth_code = '''def check_password(password):
    # BUG: this should be "< 8" not "<= 8" - an 8 character password
    # should be allowed, but right now it gets rejected.
    if len(password) <= 8:
        return False
    return True


class AuthService:
    def login(self, username, password):
        if not check_password(password):
            raise ValueError("password too short")
        return f"welcome {username}"
'''
    (src_folder / "auth.py").write_text(auth_code, encoding="utf-8")

    test_code = '''import sys
sys.path.insert(0, "src")
from auth import check_password


def test_eight_character_password_is_accepted():
    assert check_password("12345678") == True
'''
    (tests_folder / "test_auth.py").write_text(test_code, encoding="utf-8")

    agents_md = """# AGENTS.md

This is a tiny demo Python project.

- Tests are run with: python -m pytest tests/ -v
- Source code lives in src/
- Please verify any fix by re-running the tests above and checking the
  exit code is 0 before saying the task is done.
"""
    (TARGET_REPO / "AGENTS.md").write_text(agents_md, encoding="utf-8")

    print("Demo project created. It has a real bug in src/auth.py that the agent can find and fix.")
    print()



def safe_path(relative_path):
    """
    Turn a relative path like "src/auth.py" into a full path inside
    target_repo, and make sure it didn't try to escape outside that
    folder. Returns None if it's not safe.
    """
    full_path = (TARGET_REPO / relative_path).resolve()
    repo_root = TARGET_REPO.resolve()
    if repo_root not in full_path.parents and full_path != repo_root:
        return None
    return full_path


def list_files(path=".", recursive=False):
    """List files and folders inside target_repo."""
    full_path = safe_path(path)
    if full_path is None:
        return "ERROR: that path is outside the project folder, not allowed."
    if not full_path.exists():
        return f"ERROR: path does not exist: {path}"
    if not full_path.is_dir():
        return f"ERROR: not a folder: {path}"

    skip_names = {".git", "__pycache__", "node_modules", ".pytest_cache", "sessions"}
    lines = []

    if recursive:
        for folder, subfolders, files in os.walk(full_path):
            subfolders[:] = [s for s in subfolders if s not in skip_names]
            rel_folder = Path(folder).relative_to(TARGET_REPO)
            for name in sorted(files):
                lines.append(str(rel_folder / name))
    else:
        for item in sorted(full_path.iterdir()):
            if item.name in skip_names:
                continue
            rel = item.relative_to(TARGET_REPO)
            if item.is_dir():
                lines.append(f"{rel}/")
            else:
                lines.append(str(rel))

    if not lines:
        return "(empty folder)"
    return "\n".join(lines)


def read_file(path, start_line=1, end_line=None):
    """Read a file, optionally only a range of lines (so we don't dump huge files)."""
    full_path = safe_path(path)
    if full_path is None:
        return "ERROR: that path is outside the project folder, not allowed."
    if not full_path.exists():
        return f"ERROR: file does not exist: {path}"
    if not full_path.is_file():
        return f"ERROR: not a file: {path}"

    text = full_path.read_text(encoding="utf-8", errors="replace")
    all_lines = text.splitlines()
    total_lines = len(all_lines)

    if start_line < 1:
        start_line = 1
    if end_line is None:
        end_line = min(total_lines, start_line + 500)
    end_line = min(end_line, total_lines, start_line + 500)

    if start_line > total_lines:
        return f"ERROR: file only has {total_lines} lines."

    chosen_lines = all_lines[start_line - 1:end_line]
    numbered = []
    line_number = start_line
    for line_text in chosen_lines:
        numbered.append(f"{line_number}: {line_text}")
        line_number += 1

    header = f"--- {path} (lines {start_line}-{end_line} of {total_lines}) ---"
    return header + "\n" + "\n".join(numbered)


def write_file(path, content):
    """
    Overwrite (or create) a file with new content. This is a MUTATING
    action - the calling code checks for approval before calling this.
    """
    full_path = safe_path(path)
    if full_path is None:
        return "ERROR: that path is outside the project folder, not allowed."

    full_path.parent.mkdir(parents=True, exist_ok=True)
    already_existed = full_path.exists()
    full_path.write_text(content, encoding="utf-8")

    if already_existed:
        return f"Overwrote {path}"
    return f"Created {path}"


def edit_file(path, old_text, new_text=""):
    """
    Replace one piece of exact text in a file with new text. Safer than
    write_file for small changes because it fails instead of guessing if
    old_text isn't found, or is found more than once.
    This is also a MUTATING action - approval is checked before this runs.
    """
    full_path = safe_path(path)
    if full_path is None:
        return "ERROR: that path is outside the project folder, not allowed."
    if not full_path.exists():
        return f"ERROR: file does not exist: {path}"

    content = full_path.read_text(encoding="utf-8", errors="replace")
    how_many_times = content.count(old_text)

    if how_many_times == 0:
        return "ERROR: could not find that exact text in the file. Read the file again and copy it exactly."
    if how_many_times > 1:
        return f"ERROR: that text appears {how_many_times} times in the file, not unique. Add more surrounding text so it only matches once."

    new_content = content.replace(old_text, new_text, 1)
    full_path.write_text(new_content, encoding="utf-8")
    return f"Edited {path} successfully."



def list_definitions(path):
    """Show the function and class definitions in a file, with line numbers."""
    full_path = safe_path(path)
    if full_path is None:
        return "ERROR: that path is outside the project folder, not allowed."
    if not full_path.exists():
        return f"ERROR: file does not exist: {path}"

    text = full_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    found = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        line_number = i + 1
        if stripped.startswith("def ") or stripped.startswith("async def "):
            found.append(f"{line_number}: {stripped}")
        elif stripped.startswith("class "):
            found.append(f"{line_number}: {stripped}")
        elif stripped.startswith("function ") or "=> {" in stripped or "function(" in stripped:
            # very rough check for JS-style functions, in case the repo isn't Python
            found.append(f"{line_number}: {stripped}")

    if not found:
        return f"No function or class definitions found in {path}."

    return f"--- definitions in {path} ---\n" + "\n".join(found)




SAFE_COMMAND_STARTS = [
    "ls", "cat", "head", "tail", "find", "grep", "pwd", "echo", "tree",
    "git log", "git diff", "git status", "git show", "git branch",
    "pytest", "python -m pytest", "python3 -m pytest",
]


RISKY_WORDS = [
    "rm ", "mv ", "cp ", ">", "sudo", "chmod", "chown",
    "pip install", "npm install", "git push", "git commit",
    "git checkout", "git reset", "git add", "curl", "wget", "&&", "|", ";",
]


NEVER_ALLOWED = [
    "rm -rf /",
    "rm -fr /",
    "mkfs",
]


def check_if_command_is_safe(command):
    """
    Look at a shell command and decide: "safe", "ask", or "danger".
    Returns a tuple of (decision, reason_text).
    """
    command = command.strip()

    for bad_command in NEVER_ALLOWED:
        if bad_command in command:
            return "danger", f"this command ({bad_command}) is permanently blocked"

    if ".." in command:
        return "ask", "command mentions '..' which could escape the project folder"

    for risky_word in RISKY_WORDS:
        if risky_word in command:
            return "ask", f"command contains '{risky_word.strip()}' which can change things"

    for safe_start in SAFE_COMMAND_STARTS:
        if command.startswith(safe_start):
            return "safe", f"starts with known safe command '{safe_start}'"

    return "ask", "this command is not on the known-safe list"


def run_command(command):
    """
    Actually run a shell command inside target_repo, and return what
    happened. This function does NOT check safety or ask for approval -
    that already happened before this function gets called.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(TARGET_REPO),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: command took too long and was stopped after {COMMAND_TIMEOUT} seconds."

    output_text = f"$ {command}\nexit_code: {result.returncode}\n"
    if result.stdout.strip():
        output_text += f"--- output ---\n{result.stdout.strip()}\n"
    if result.stderr.strip():
        output_text += f"--- errors ---\n{result.stderr.strip()}\n"
    return output_text




def todos_file_path(session_id):
    return SESSIONS_FOLDER / session_id / "todos.json"


def load_todos(session_id):
    path = todos_file_path(session_id)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_todos(session_id, todos):
    path = todos_file_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(todos, indent=2), encoding="utf-8")


def add_todos(session_id, items):
    """
    Add new todo items. Each item must be a dictionary with "title",
    "description", and "verification_method". If verification_method
    is too short/vague, the item is rejected.
    """
    todos = load_todos(session_id)
    added_count = 0
    messages = []

    for item in items:
        title = item.get("title", "").strip()
        description = item.get("description", "").strip()
        verification_method = item.get("verification_method", "").strip()

        if not title or not description or not verification_method:
            messages.append(f"REJECTED (missing info): {item}")
            continue
        if len(verification_method) < 8:
            messages.append(f"REJECTED '{title}': verification_method is too vague, be specific.")
            continue

        new_id = len(todos) + 1
        todos.append({
            "id": new_id,
            "title": title,
            "description": description,
            "verification_method": verification_method,
            "status": "pending",
            "evidence": "",
        })
        added_count += 1

    save_todos(session_id, todos)

    result_text = f"Added {added_count} todo(s)."
    if messages:
        result_text += "\n" + "\n".join(messages)
    return result_text


def get_todos(session_id, status=None):
    """List all todos, or only todos with a certain status."""
    todos = load_todos(session_id)
    if status:
        todos = [t for t in todos if t["status"] == status]

    if not todos:
        return "(no todos)"

    lines = []
    for t in todos:
        line = f"[{t['id']}] ({t['status']}) {t['title']} - verify: {t['verification_method']}"
        if t["evidence"]:
            line += f" | evidence: {t['evidence']}"
        lines.append(line)
    return "\n".join(lines)


def mark_todo(session_id, todo_id, status, evidence=""):
    """
    Change a todo's status. If status is "completed", evidence is
    required and must look like real output (mentions "exit_code" or
    similar), not just a vague sentence.
    """
    todos = load_todos(session_id)
    found_todo = None
    for t in todos:
        if t["id"] == todo_id:
            found_todo = t
            break

    if found_todo is None:
        return f"ERROR: no todo with id {todo_id}"

    if status == "completed":
        if not evidence.strip():
            return f"REJECTED: you must give real evidence to mark todo {todo_id} completed. Run the verification step for real first."
        evidence_looks_real = (
            "exit_code" in evidence.lower()
            or "passed" in evidence.lower()
            or "failed" in evidence.lower()
            or "$" in evidence
        )
        if not evidence_looks_real:
            return f"REJECTED: evidence '{evidence}' does not look like real command output. Re-run the actual check and paste the result."

    found_todo["status"] = status
    found_todo["evidence"] = evidence
    save_todos(session_id, todos)
    return f"Todo {todo_id} is now '{status}'."


def plan_is_finished(session_id):
    """True only if there ARE todos, and every single one is completed or blocked."""
    todos = load_todos(session_id)
    if not todos:
        return False
    for t in todos:
        if t["status"] not in ("completed", "blocked"):
            return False
    return True



TOOLS_FOR_MODEL = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files/folders in the project. Use this first to explore.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Folder path. Default '.' for the top folder."},
                    "recursive": {"type": "boolean", "description": "If true, also look inside subfolders."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents. Use start_line/end_line for big files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_definitions",
            "description": "Show the functions and classes in a file with line numbers, without reading the whole file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a shell command in the project folder. Use this to search code "
                "(grep), check git history, and run tests. Safe commands run right "
                "away. Risky commands will pause and ask the human for a yes/no first "
                "- just call this tool normally and read what comes back."
            ),
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Overwrite or create a file with new content. Will ask the human for approval first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace one exact piece of text in a file with new text. Will ask the human for approval first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_todos",
            "description": "Add items to your plan/todo list. Each item needs title, description, and a clear verification_method.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "verification_method": {"type": "string"},
                            },
                            "required": ["title", "description", "verification_method"],
                        },
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_todos",
            "description": "See your current todo list, optionally filtered by status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "blocked"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_todo",
            "description": "Update a todo's status. To mark 'completed' you MUST give real evidence (actual command output), not just a guess.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "integer"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "blocked"]},
                    "evidence": {"type": "string"},
                },
                "required": ["todo_id", "status"],
            },
        },
    },
]


TOOLS_THAT_ALWAYS_NEED_APPROVAL = ["write_file", "edit_file"]



def ask_human_yes_no(description_of_action):
    """
    Show the human exactly what is about to happen and wait for them to
    type y or n. Returns True for yes, False for no.
    """
    print()
    print("=" * 60)
    print("APPROVAL NEEDED - this could change the project files.")
    print("=" * 60)
    print(description_of_action)
    print("-" * 60)
    while True:
        answer = input("Allow this? (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please type y or n.")


def get_approval_if_needed(tool_name, tool_arguments):
    """
    Decide if this tool call needs approval, and if so, ask for it.
    Returns (is_allowed, reason_text).
    """
    if tool_name in TOOLS_THAT_ALWAYS_NEED_APPROVAL:
        if tool_name == "write_file":
            description = f"Write file: {tool_arguments.get('path')}\n\nNew content:\n{tool_arguments.get('content', '')[:500]}"
        else:  # edit_file
            description = (
                f"Edit file: {tool_arguments.get('path')}\n\n"
                f"REMOVE:\n{tool_arguments.get('old_text', '')}\n\n"
                f"ADD:\n{tool_arguments.get('new_text', '')}"
            )
        approved = ask_human_yes_no(description)
        return approved, "file changes always need approval"

    if tool_name == "run_command":
        command = tool_arguments.get("command", "")
        decision, reason = check_if_command_is_safe(command)

        if decision == "danger":
            return False, f"BLOCKED forever: {reason}"

        if decision == "safe":
            return True, reason

        
        description = f"Run this command:\n  $ {command}\n\nWhy it needs approval: {reason}"
        approved = ask_human_yes_no(description)
        return approved, reason

    
    return True, "read-only, no approval needed"



def run_the_tool(tool_name, tool_arguments, session_id):
    """
    Given a tool name and its arguments, first check approval, then
    actually run the tool and return the text result that goes back to
    the AI model.
    """
    allowed, reason = get_approval_if_needed(tool_name, tool_arguments)
    if not allowed:
        return f"DENIED ({reason})"

    try:
        if tool_name == "list_files":
            return list_files(
                tool_arguments.get("path", "."),
                tool_arguments.get("recursive", False),
            )

        if tool_name == "read_file":
            return read_file(
                tool_arguments["path"],
                tool_arguments.get("start_line", 1),
                tool_arguments.get("end_line"),
            )

        if tool_name == "list_definitions":
            return list_definitions(tool_arguments["path"])

        if tool_name == "run_command":
            return run_command(tool_arguments["command"])

        if tool_name == "write_file":
            return write_file(tool_arguments["path"], tool_arguments["content"])

        if tool_name == "edit_file":
            return edit_file(
                tool_arguments["path"],
                tool_arguments["old_text"],
                tool_arguments.get("new_text", ""),
            )

        if tool_name == "add_todos":
            return add_todos(session_id, tool_arguments["items"])

        if tool_name == "get_todos":
            return get_todos(session_id, tool_arguments.get("status"))

        if tool_name == "mark_todo":
            return mark_todo(
                session_id,
                tool_arguments["todo_id"],
                tool_arguments["status"],
                tool_arguments.get("evidence", ""),
            )

        return f"ERROR: unknown tool '{tool_name}'"

    except KeyError as missing_key:
        return f"ERROR: missing required argument {missing_key}"
    except Exception as e:
        return f"ERROR: something went wrong running this tool: {e}"



def messages_file_path(session_id):
    return SESSIONS_FOLDER / session_id / "messages.json"


SYSTEM_PROMPT = """You are Code Scout, a coding agent. You have been given a project folder
to work in and a task to do. Nobody has told you exactly which file or
line has the problem - you need to find that yourself.

Rules to follow:
1. SEARCH FIRST. Use run_command with grep, and use list_files and
   list_definitions, to find the right code BEFORE reading whole files.
2. MAKE A PLAN. Once you understand the task, call add_todos with your
   plan. Each todo needs a real, specific verification_method.
3. VERIFY, DON'T GUESS. After you make a change, actually run the
   tests again with run_command and look at the real result. Only call
   mark_todo with status "completed" if you have real proof (like
   exit_code: 0) as your evidence.
4. MENTION FILE AND LINE NUMBERS when you explain what you found or
   changed.
5. Some actions need human approval (a yes/no question) - this happens
   automatically, you don't need to ask permission yourself in words,
   just call the tool and read what it says back.
6. KEEP GOING until every todo is either "completed" (with real proof)
   or "blocked" (with a reason). Don't stop in the middle.
7. If there is an AGENTS.md file in the project, read it early and
   follow what it says (like which command runs the tests).

When you are truly done, write your final answer in plain text (no
more tool calls): explain what was wrong, what you changed, and the
exact command + result that proves it works. If you could not verify
something, say that honestly instead of pretending it's fixed.
"""


def load_or_start_messages(session_id):
    """Load saved chat history for this session, or start a new conversation."""
    path = messages_file_path(session_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass  
    system_text = SYSTEM_PROMPT + f"\n\nProject folder: {TARGET_REPO}\n"

    agents_md_path = TARGET_REPO / "AGENTS.md"
    if agents_md_path.exists():
        agents_md_text = agents_md_path.read_text(encoding="utf-8", errors="replace")
        system_text += "\n--- AGENTS.md for this project ---\n" + agents_md_text

    return [{"role": "system", "content": system_text}]


def save_messages(session_id, messages):
    path = messages_file_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(messages, indent=2), encoding="utf-8")


def list_saved_sessions():
    if not SESSIONS_FOLDER.exists():
        return []
    return sorted(p.name for p in SESSIONS_FOLDER.iterdir() if p.is_dir())




class Agent:
    def __init__(self, session_id=None):
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]
        self.session_id = session_id
        self.messages = load_or_start_messages(session_id)
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY"),
        )

    def run_task(self, task_text):
        """
        Send one task to the agent and let it work (calling tools as
        many times as it needs) until it gives a final plain-text
        answer, or until it hits the MAX_STEPS safety limit.
        """
        self.messages.append({"role": "user", "content": task_text})

        for step_number in range(MAX_STEPS):
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=self.messages,
                tools=TOOLS_FOR_MODEL,
            )
            reply = response.choices[0].message
            tool_calls = reply.tool_calls

            if tool_calls:
                # The model wants to use one or more tools.
                assistant_message = {"role": "assistant", "content": reply.content or ""}
                assistant_message["tool_calls"] = []
                for call in tool_calls:
                    assistant_message["tool_calls"].append({
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments},
                    })
                self.messages.append(assistant_message)

                for call in tool_calls:
                    try:
                        arguments = json.loads(call.function.arguments or "{}")
                    except Exception:
                        arguments = {}

                    print(f"\n[using tool] {call.function.name}({arguments})")
                    result_text = run_the_tool(call.function.name, arguments, self.session_id)
                    print(f"[result] {result_text[:400]}")

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result_text,
                    })

                save_messages(self.session_id, self.messages)
                continue  

            
            self.messages.append({"role": "assistant", "content": reply.content or ""})
            save_messages(self.session_id, self.messages)

            todos_exist = len(load_todos(self.session_id)) > 0
            if todos_exist and not plan_is_finished(self.session_id):
                self.messages.append({
                    "role": "user",
                    "content": (
                        "Your todo list is not finished yet (some items are still "
                        "pending or in_progress). Keep working, or mark an item "
                        "'blocked' with a reason if you really cannot finish it."
                    ),
                })
                continue

            return reply.content or "(no answer given)"

        return (
            f"Stopped after {MAX_STEPS} steps without finishing the plan. "
            "This is an honest 'not finished' result, not a made-up success."
        )


class REPLAgent(Agent):
    """Same as Agent, but adds an interactive chat loop (type many tasks in a row)."""

    def chat_loop(self):
        print(f"Code Scout - session '{self.session_id}'")
        print(f"Working in: {TARGET_REPO}")
        print("Type a task and press enter. Type 'exit' to quit.\n")

        while True:
            try:
                task_text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye! Your session is saved as:", self.session_id)
                break

            if not task_text:
                continue
            if task_text.lower() in ("exit", "quit"):
                print("Session saved as:", self.session_id)
                break

            answer = self.run_task(task_text)
            print(f"\nagent> {answer}\n")



def main():
    load_dotenv()  

    make_demo_repo_if_missing()

    arguments = sys.argv[1:]

    if "--list-sessions" in arguments:
        sessions = list_saved_sessions()
        if not sessions:
            print("(no saved sessions yet)")
        else:
            for s in sessions:
                print(s)
        return

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY is not set.")
        print("Copy .env.example to .env and put your key in it.")
        return

    
    session_id = None
    if "--session" in arguments:
        index = arguments.index("--session")
        if index + 1 < len(arguments):
            session_id = arguments[index + 1]
            del arguments[index:index + 2]

    
    leftover_text = " ".join(a for a in arguments if not a.startswith("--"))

    if leftover_text.strip():
        agent = Agent(session_id=session_id)
        answer = agent.run_task(leftover_text.strip())
        print("\n" + "=" * 60)
        print("FINAL ANSWER")
        print("=" * 60)
        print(answer)
    else:
        agent = REPLAgent(session_id=session_id)
        agent.chat_loop()


if __name__ == "__main__":
    main()
