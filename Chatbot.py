import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

class ChatAgent:
    def __init__(self, model):
        self.model = model
        self.message = [
            {"role":"system", "content": "You are a helpful assistant. "}
        ]
        print("Chat started. Type 'exit' to quit.\n")


    def add_user_message(self, text):
        self.message.append({"role": "user", "content": text})

        
    def add_assistant_message(self):
        response = client.chat.completions.create(
            model = self.model,
            messages = self.message
            )
        reply = response.choices[0].message.content
        print(reply)
        self.message.append({"role": "assistant", "content": reply})


    def compact_history(self):
        old_messages = self.message[1:]

        summary_prompt = [
            {
                "role": "system",
                "content": "Summarize this conversation briefly."
            }
        ] + old_messages
        response = client.chat.completions.create(
            model = self.model,
            messages = summary_prompt
        )
        summary = response.choices[0].message.content
        self.message = [
        {"role":"system", "content":"You are a helpful assistant."},
        {"role":"system","content":f"Conversation Summary: {summary}"}] 


    def run(self):
        while True:
            user_input = input("\nuser: ")
            
            if user_input.lower() in ["quit", "exit"]:
                print("Goodbye!")
                break

            if user_input.lower() in ["reset"]:
                self.message = [
                    {"role": "system", "content": "You are a helpful assistant"}
                ]
                print("History cleared")
                continue
            if len(self.message) > 11:
                self.compact_history()

            self.add_user_message(user_input)
            self.add_assistant_message()


if __name__ == "__main__":
    agent = ChatAgent("openrouter/free")
    agent.run()

