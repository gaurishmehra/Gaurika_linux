from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import threading
import subprocess

load_dotenv()
Groq = os.getenv("GROQ_API_KEY")
Groq_base_url = "https://api.groq.com/openai/v1"

tools = [
    {
        "type": "function",
        "function": {
            "name": "linux",
            "description": "Execute a single Linux command on the user's machine on their behalf.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The Linux command to execute.",
                    }
                },
                "required": ["command"],
            },
        },
    }
]

client = OpenAI(api_key=Groq, base_url=Groq_base_url)

def load_context_history(filename="context_history.json"):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_context_history(context_history, filename="context_history.json"):
    with open(filename, "w") as f:
        json.dump(context_history, f, indent=2)

def execute_linux_command(command):
    try:
        output = subprocess.check_output(command, shell=True, text=True, stderr=subprocess.STDOUT)
        return output  # Return the output directly
    except subprocess.CalledProcessError as e:
        return f"Command '{command}' failed with error:\n{e.output}"

def chat_stream(messages, model="llama-3.1-70b-versatile", temperature=0.75, max_tokens=4096, tool_choice="auto"):
    response = client.chat.completions.create(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        tools=tools,
        tool_choice=tool_choice,
    )
    
    full_response = ""
    tool_calls = None
    for chunk in response:
        if chunk.choices[0].delta.content is not None:
            content = chunk.choices[0].delta.content
            print(content, end="", flush=True)
            full_response += content
        if chunk.choices[0].delta.tool_calls:
            tool_calls = chunk.choices[0].delta.tool_calls
    
    print()  # New line after the full response
    return full_response, tool_calls

def handle_tool_calls(tool_calls):
    if tool_calls:
        print("\nTool Calls:", tool_calls)
        for tool_call in tool_calls:
            if tool_call.function.name == "linux":
                function_args = json.loads(tool_call.function.arguments)
                command = function_args.get("command")
                
                # Execute command in a separate thread
                thread = threading.Thread(target=execute_and_return_command_result, args=(command, tool_call.id))
                thread.start()
                thread.join()  # Wait for the thread to complete
    return None

def execute_and_return_command_result(command, tool_call_id):
    result = execute_linux_command(command)
    context_history.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": "linux",
        "content": result  # Send the result to the LLM
    })

def main():
    global context_history  # Declare context_history as global
    context_history = load_context_history()
    
    system_message = """You are a helpful assistant. You may choose not to call any tools. 
    If you need to execute a command, use the `linux` tool and provide a single command. 
    For multiple commands, chain them using `&&`.
    Let the user know what command you executed and then share the results with the user. 
    Please do not execute any command that may be harmful before getting explicit permission from the user.
    While executing commands, use standard Linux commands and assume a standard Linux folder structure."""

    if not context_history:
        context_history.append({"role": "system", "content": system_message})
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit", "bye"]:
            break
        
        context_history.append({"role": "user", "content": user_input})
        
        assistant_response, tool_calls = chat_stream(context_history)
        
        handle_tool_calls(tool_calls)
        
        # Get a follow-up response from the assistant after tool execution
        if tool_calls:
            follow_up_response, _ = chat_stream(context_history, tool_choice="none")
            assistant_response += "\n" + follow_up_response
        
        context_history.append({"role": "assistant", "content": assistant_response})
        
        save_context_history(context_history)

if __name__ == "__main__":
    main()