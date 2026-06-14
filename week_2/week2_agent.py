import os
import json
import time
import random
import datetime
import requests
import trafilatura
from openai import OpenAI
from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog, Static
from textual.binding import Binding

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY", ""),
)

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")

# the model we are using
MODEL = "openrouter/free"

def web_search(query, num_results=5):

    if not SERPER_API_KEY:
        return json.dumps({"error": "SERPER_API_KEY is not set in .env file"})

    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json"
            },
            json={"q": query, "num": num_results},
            timeout=10
        )

        data = response.json()

        results = []
        for item in data.get("organic", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })

        return json.dumps({"results": results})

    except requests.exceptions.Timeout:
        return json.dumps({"error": "search timed out, try again"})
    except Exception as e:
        return json.dumps({"error": f"search failed: {e}"})


def web_fetch(url, max_chars=4000):

    try:
        time.sleep(random.uniform(1, 2))

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MyResearchBot/1.0)"
        }
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code != 200:
            return json.dumps({"error": f"got status code {response.status_code} from {url}"})

        text = trafilatura.extract(response.text)

        if not text:
            text = response.text[:max_chars]

        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [cut off here to save tokens]"

        return json.dumps({"url": url, "content": text})

    except requests.exceptions.Timeout:
        return json.dumps({"error": f"page took too long to load: {url}"})
    except Exception as e:
        return json.dumps({"error": f"could not fetch page: {e}"})


def discover_papers(query):

    try:
        response = requests.post(
            "https://mcp.alphaxiv.org/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "discover_papers",
                    "arguments": {
                        "query": query,
                        "max_results": 5
                    }
                }
            },
            headers={"Content-Type": "application/json"},
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            result = data.get("result", data)
            return json.dumps(result)

        return json.dumps({"error": f"alphaxiv returned status {response.status_code}"})

    except requests.exceptions.Timeout:
        return json.dumps({"error": "alphaxiv timed out"})
    except Exception as e:
        return json.dumps({"error": f"could not search papers: {e}"})


def get_paper_content(paper_id):
    # get the full content of a specific paper using its arxiv id
    # we truncate to 4000 chars to keep token usage under control

    try:
        response = requests.post(
            "https://mcp.alphaxiv.org/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "get_paper_content",
                    "arguments": {
                        "paper_id": paper_id
                    }
                }
            },
            headers={"Content-Type": "application/json"},
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            result = data.get("result", data)
            content = json.dumps(result)

            if len(content) > 4000:
                content = content[:4000] + "... [truncated]"

            return content

        return json.dumps({"error": f"alphaxiv returned status {response.status_code}"})

    except requests.exceptions.Timeout:
        return json.dumps({"error": "alphaxiv timed out"})
    except Exception as e:
        return json.dumps({"error": f"could not get paper: {e}"})


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Use this first before fetching pages. Returns titles, links, and short snippets from Google.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "what to search for"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "how many results to return, between 1 and 10",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Read the full content of a webpage. Use this after web_search to read the actual articles. Prefer official sites and known publishers over forums.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "the full url to fetch, must start with https://"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "discover_papers",
            "description": "Search for academic research papers on arxiv. Use this when the question is about research, studies, or scientific findings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "research topic to search for"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_paper_content",
            "description": "Read the full content of a specific paper using its arxiv id. Use this after discover_papers when you want to read a paper in detail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "string",
                        "description": "the arxiv paper id, for example 2210.03629"
                    }
                },
                "required": ["paper_id"]
            }
        }
    }
]



# SYSTEM PROMPT

SYSTEM_PROMPT = """You are a research assistant that can search the web and find academic papers.

How to research a question:
1. Use web_search to find relevant pages
2. Use web_fetch to read the most useful pages in full
3. For research questions also use discover_papers and get_paper_content
4. Then write a clear answer using what you found, and mention your sources

Try to use good sources like official websites, well known news sites, or academic papers.
Avoid low quality sources like random forums unless there is nothing better.

Keep your final answer focused and easy to read. Always say where your information came from."""



def dispatch(tool_call):
    name = tool_call.function.name

    try:
        arguments = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        return json.dumps({"error": "could not read tool arguments"})


    if name == "web_search":
        return web_search(
            query=arguments.get("query", ""),
            num_results=arguments.get("num_results", 5)
        )
    elif name == "web_fetch":
        return web_fetch(url=arguments.get("url", ""))
    elif name == "discover_papers":
        return discover_papers(query=arguments.get("query", ""))
    elif name == "get_paper_content":
        return get_paper_content(paper_id=arguments.get("paper_id", ""))
    else:
        return json.dumps({"error": f"dont know this tool: {name}"})



def run_agent(user_message, history, on_tool_call=None):
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages = messages + history
    messages.append({"role": "user", "content": user_message})

    for i in range(10):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto"
            )
        except Exception as e:
            return f"API call failed: {e}"

        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        if finish_reason != "tool_calls" or not message.tool_calls:
            return message.content or "no response"

        messages.append(message)

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = tool_call.function.arguments
            if on_tool_call:
                on_tool_call(tool_name, tool_args)

            result = dispatch(tool_call)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })


    return "hit the max number of steps, please try a simpler question"



class ResearchApp(App):

    CSS = """
    RichLog {
        height: 1fr;
        border: solid $accent;
        padding: 1 2;
    }

    #status {
        height: 1;
        background: $surface;
        color: $warning;
        padding: 0 2;
        display: none;
    }

    #status.visible {
        display: block;
    }

    Input {
        dock: bottom;
        border: solid $accent;
    }
    """

    BINDINGS = [
        Binding("ctrl+l", "clear_display", "Clear Display"),
        Binding("ctrl+k", "clear_history", "Clear History"),
        Binding("ctrl+s", "save_chat", "Save Chat"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.history = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="chat-log", wrap=True, markup=True)
        yield Static("", id="status")
        yield Input(placeholder="ask a research question and press enter...")
        yield Footer()

    def on_mount(self):
        self.title = "CHATBOT"
        self.query_one(Input).focus()

        log = self.query_one(RichLog)
        log.write("[bold]Welcome to Research Agent![/bold]")
        log.write("[dim]I can search the web and find academic papers to answer your questions.[/dim]")
        log.write("")
        log.write("[dim]Ctrl+L = clear screen  |  Ctrl+K = clear history  |  Ctrl+S = save  |  Ctrl+Q = quit[/dim]")
        log.write("")
        log.write("[dim]Try asking: What were the main announcements at Google I/O 2024?[/dim]")
        log.write("[dim]Try asking: Find recent papers on chain-of-thought prompting[/dim]")
        log.write("")

    def on_input_submitted(self, event: Input.Submitted):
        user_message = event.value.strip()

        if not user_message:
            return

        self.query_one(Input).clear()

        log = self.query_one(RichLog)
        log.write(f"[You] {user_message}")
        log.write("")

        self._show_status("thinking...")

        self.history.append({"role": "user", "content": user_message})

        self.run_worker(
            lambda: self._get_response(user_message),
            thread=True
        )

    def _get_response(self, user_message):
        def on_tool_call(name, args):
            try:
                a = json.loads(args)
                if name == "web_search":
                    msg = f"searching: {a.get('query', '')}"
                elif name == "web_fetch":
                    msg = f"reading page: {a.get('url', '')[:60]}..."
                elif name == "discover_papers":
                    msg = f"searching papers: {a.get('query', '')}"
                elif name == "get_paper_content":
                    msg = f"reading paper: {a.get('paper_id', '')}"
                else:
                    msg = f"using tool: {name}"

                self.call_from_thread(self._show_status, msg)
                self.call_from_thread(
                    self.query_one(RichLog).write,
                    f" -> {msg} "
                )
            except Exception:
                pass

        try:
            reply = run_agent(
                user_message=user_message,
                history=self.history[:-1],
                on_tool_call=on_tool_call
            )

            self.history.append({"role": "assistant", "content": reply})

            if len(self.history) > 20:
                self.history = self.history[-20:]

            self.call_from_thread(self._show_reply, reply)

        except Exception as e:
            self.call_from_thread(self._show_error, str(e))

    def _show_reply(self, reply):
        self._hide_status()
        log = self.query_one(RichLog)
        log.write(f"[Agent] {reply}")
        log.write("")

    def _show_error(self, error):
        self._hide_status()
        log = self.query_one(RichLog)
        log.write(f"[Error] {error}")
        log.write("")

    def _show_status(self, msg):
        s = self.query_one("#status")
        s.update(f"  {msg}")
        s.add_class("visible")

    def _hide_status(self):
        s = self.query_one("#status")
        s.update("")
        s.remove_class("visible")

    def action_clear_display(self):
        self.query_one(RichLog).clear()
        self.query_one(RichLog).write("[dim]screen cleared, history still saved[/dim]")

    def action_clear_history(self):
        self.query_one(RichLog).clear()
        self.history = []
        self.query_one(RichLog).write("[dim]history cleared, starting fresh[/dim]")

    def action_save_chat(self):
        if not self.history:
            self.query_one(RichLog).write("[dim]nothing to save yet[/dim]")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chat_{timestamp}.txt"

        try:
            with open(filename, "w") as f:
                f.write(f"research chat saved at {timestamp}\n")
                f.write("=" * 40 + "\n\n")
                for msg in self.history:
                    role = "You" if msg["role"] == "user" else "Agent"
                    f.write(f"[{role}]\n{msg['content']}\n\n")

            self.query_one(RichLog).write(f"saved to {filename}")
        except Exception as e:
            self.query_one(RichLog).write(f"could not save: {e}")


if __name__ == "__main__":
    ResearchApp().run()