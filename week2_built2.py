import os
import json
import math
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

MODEL = "openrouter/free"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Returns the current weather for a given city. "
                "Call this whenever the user asks about weather, temperature, or climate. "
                "Do not guess weather. Always call this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "The city name, e.g. 'Delhi' or 'San Francisco'",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit. Default to celsius.",
                    },
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluates a mathematical expression and returns the result. "
                "Use this for any arithmetic the user asks about. "
                "Pass the expression as a string, e.g. '1337 * 42 + 7'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "A Python arithmetic expression, e.g. '100 / 4 + 3'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]
def get_weather(city, unit):
    
    weather_data = {
        "london": {"temp_celsius": 15, "condition": "Cloudy"},
        "delhi":  {"temp_celsius": 38, "condition": "Sunny"},
        "mumbai": {"temp_celsius": 32, "condition": "Humid"},
        "paris":  {"temp_celsius": 18, "condition": "Partly Cloudy"},
    }
    city_lower = city.lower()
    if city_lower in weather_data:
        data = weather_data[city_lower]
        temp = data["temp_celsius"]
        if unit == "fahrenheit":
            temp = (temp *9/5) + 32
        return json.dumps({
            "city": city,
            "temperature": temp,
            "unit": unit,
            "condition": data["condition"]
        })
    return json.dumps({"error": f"No weather data for {city}"})

def calculate(expression):
    try:
        allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
        result = eval(expression, {"__builtins__": {}}, allowed)
        return json.dumps({"expression": expression, "result": result})
    except Exception as e:
        return json.dumps({"error": str(e)})
    
def dispatch(tool_call):
    name = tool_call.function.name
    try:
        arguments = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid arguments"})

    print(f"\n[Tool call: {name}({arguments})]")

    if name == "get_weather":
        result = get_weather(
            city=arguments.get("city"),
            unit=arguments.get("unit", "celsius")
        )
    elif name == "calculate":
        result = calculate(
            expression=arguments.get("expression")
        )
    else:
        result = json.dumps({"error": f"Unknown tool: {name}"})

    print(f"[Tool result: {result}]")
    return result

def run_agent(user_message):
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Use tools when needed."},
        {"role": "user",   "content": user_message}
    ]

    for i in range(10):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,           
                tool_choice="auto"     
            )
        except Exception as e:
            print(f"API error: {e}")
            break

        message = response.choices[0].message
        if response.choices[0].finish_reason != "tool_calls":
            print("\nAgent:", message.content)
            break

        messages.append(message) 
        for tool_call in message.tool_calls:
            result = dispatch(tool_call)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })

if __name__ == "__main__":
    print("test1 : weather")
    run_agent("What is the weather in Delhi in celsius?")

    print("\nTest 2: Calculate")
    run_agent("What is 15 multiplied by 37?")

    print("\nTest 3: Multi tool")
    run_agent("What is the weather in London and what is sqrt(144)?")



