from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog

class ChatApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    RichLog {
        border: solid green;
        height: 1fr;
    }
    Input {
        dock: bottom;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="log", wrap=True, markup=True)
        yield Input(placeholder="Type a message...")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#log", RichLog).write("[bold green]Chat started.[/bold green]")

if __name__ == "__main__":
    ChatApp().run()