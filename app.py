import requests
import os
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from selectolax.parser import HTMLParser
from urllib.parse import quote_plus
from collections import deque
import socket
from openai import OpenAI
from dotenv import load_dotenv
import json
import subprocess
import datetime
import schedule
import threading

# Load environment variables from .env file
load_dotenv()
Groq = os.getenv("GROQ_API_KEY")
Groq_base_url = "https://api.groq.com/openai/v1"

# Set a global socket timeout
socket.setdefaulttimeout(1)

# Define tools for the assistant
tools = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
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
    },
    {
        "type": "function",
        "function": {
            "name": "WebTool",
            "description": "Perform a web search and retrieve relevant content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to use.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_task",
            "description": "Schedule a Linux command to run at regular intervals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "A unique name for the scheduled task.",
                    },
                    "command": {
                        "type": "string",
                        "description": "The Linux command to be executed.",
                    },
                    "interval": {
                        "type": "integer",
                        "description": "The interval in seconds between each execution of the task.",
                    }
                },
                "required": ["task_name", "command", "interval"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_scheduled_task",
            "description": "Remove a previously scheduled task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "The name of the task to be removed.",
                    }
                },
                "required": ["task_name"],
            },
        },
    }
]

# Initialize OpenAI client
client = OpenAI(api_key=Groq, base_url=Groq_base_url)

# Global variables
context_history = []
scheduled_tasks = {}

def load_context_history(filename="context_history.json"):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_context_history(context_history, filename="context_history.json"):
    with open(filename, "w") as f:
        json.dump(context_history, f, indent=2)

def execute_linux_command(command, trust_mode):
    """Executes a Linux command based on the trust mode."""
    if trust_mode == "full":
        try:
            output = subprocess.check_output(command, shell=True, text=True, stderr=subprocess.STDOUT)
            return output
        except subprocess.CalledProcessError as e:
            return f"Command '{command}' failed with error:\n{e.output}"
    elif trust_mode == "half":
        user_input = input(f"\nThe assistant suggests running the following command:\n'{command}'\nDo you want to execute this command? (y/n): ").strip().lower()
        if user_input == "y":
            try:
                output = subprocess.check_output(command, shell=True, text=True, stderr=subprocess.STDOUT)
                return output
            except subprocess.CalledProcessError as e:
                return f"Command '{command}' failed with error:\n{e.output}"
        else:
            return "Command execution disallowed by the user."
    else:  # trust_mode == "none"
        return "Command execution is disabled in this trust mode."

def get_system_info():
    """Retrieves basic system information."""
    info = {}
    info['OS'] = subprocess.check_output('uname -s', shell=True, text=True).strip()
    info['Kernel'] = subprocess.check_output('uname -r', shell=True, text=True).strip()
    info['CPU'] = subprocess.check_output('lscpu | grep "Model name" | cut -d ":" -f 2', shell=True, text=True).strip()
    info['Memory'] = subprocess.check_output('free -h | awk \'/^Mem:/ {print $2}\'', shell=True, text=True).strip()
    return json.dumps(info, indent=2)

def chat_stream(messages, model="llama-3.1-70b-versatile", temperature=0.75, max_tokens=4096, tool_choice="auto"):
    """Stream response from the AI model."""
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

def save_command_history(command, output, filename="command_history.txt"):
    with open(filename, "a") as f:
        f.write(f"Time: {datetime.datetime.now()}\n")
        f.write(f"Command: {command}\n")
        f.write(f"Output:\n{output}\n")
        f.write("-" * 50 + "\n")

def handle_tool_calls(tool_calls, trust_mode):
    """Processes and executes tool calls made by the assistant based on the trust mode."""
    if tool_calls:
        print("\nTool Calls:", tool_calls)
        for tool_call in tool_calls:
            if tool_call.function.name == "execute_command":
                function_args = json.loads(tool_call.function.arguments)
                command = function_args.get("command")

                result = execute_linux_command(command, trust_mode)
                print(f"\nCommand: {command}\nResult:\n{result}")

                save_command_history(command, result)

                context_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "execute_command",
                    "content": result 
                })
            elif tool_call.function.name == "WebTool":
                function_args = json.loads(tool_call.function.arguments)
                query = function_args.get("query")

                result = WebTool(query)
                print(f"\nWeb Search Query: {query}\nResult:\n{result[:500]}...")  # Print first 500 characters

                context_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "WebTool",
                    "content": result 
                })
            elif tool_call.function.name == "schedule_task":
                function_args = json.loads(tool_call.function.arguments)
                task_name = function_args.get("task_name")
                command = function_args.get("command")
                interval = function_args.get("interval")

                schedule_task(task_name, command, interval)

                context_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "schedule_task",
                    "content": f"Task '{task_name}' scheduled to run command '{command}' every {interval} seconds."
                })
            elif tool_call.function.name == "remove_scheduled_task":
                function_args = json.loads(tool_call.function.arguments)
                task_name = function_args.get("task_name")

                remove_scheduled_task(task_name)

                context_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "remove_scheduled_task",
                    "content": f"Task '{task_name}' removed from schedule."
                })
    return None

def get_user_preferences(filename="user_pref.json"):
    """Loads or prompts for user preferences and saves them if necessary."""
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    else:
        user_name = input("Enter your name: ")
        linux_username = input("Enter your Linux username: ")
        linux_distro = input("Enter your Linux distribution (e.g., Ubuntu, Fedora, Arch): ")
        while True:
            trust_mode = input("Enter your trust mode (full, half, none): ").strip().lower()
            if trust_mode in ["full", "half", "none"]:
                break
            else:
                print("Invalid trust mode. Please enter 'full', 'half', or 'none'.")

        user_preferences = {
            "name": user_name,
            "linux_username": linux_username,
            "linux_distro": linux_distro,
            "trust_mode": trust_mode
        }

        with open(filename, "w") as f:
            json.dump(user_preferences, f, indent=2)

        return user_preferences

# WebTool implementation
def google_search(query, num_results=10, num_threads=12):
    encoded_query = quote_plus(query)
    base_url = "https://www.google.com/search"
    urls = [f"{base_url}?q={encoded_query}&start={i}" for i in range(0, min(num_results * 2, 100), 10)]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    result_urls = deque(maxlen=num_results)

    def fetch_search_page(session, url):
        try:
            with session.get(url, headers=headers, timeout=1, stream=True) as response:
                if response.status_code == 200:
                    content = ''
                    for chunk in response.iter_content(chunk_size=1024):
                        content += chunk.decode('utf-8', errors='ignore')
                        if len(re.findall(r'href="(https?://[^"]+)"', content)) >= 10:
                            break
                    return content
        except requests.RequestException:
            pass
        return None

    def parse_search_urls(content):
        if not content:
            return []
        urls = re.findall(r'href="(https?://[^"]+)"', content)
        return [url.split('&')[0] for url in urls 
                if not url.startswith(("https://www.google.", "https://google.", "https://webcache.googleusercontent.com"))]

    with requests.Session() as session:
        session.headers.update(headers)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            future_to_url = {executor.submit(fetch_search_page, session, url): url for url in urls}
            for future in as_completed(future_to_url):
                content = future.result()
                if content:
                    result_urls.extend(parse_search_urls(content))
                    if len(result_urls) >= num_results:
                        for f in future_to_url:
                            f.cancel()
                        break

    return list(result_urls)[:num_results]

def fetch_url(session, url, timeout=3):
    try:
        response = session.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
        return response.text
    except requests.RequestException:
        return ""

def extract_content(html_content, max_length=100000):
    try:
        tree = HTMLParser(html_content)
        if tree.body is None:
            return ""

        paragraphs = tree.css("p, article, section")
        text = ' '.join(p.text() for p in paragraphs if p.text())
        return text[:max_length]
    except Exception:
        return ""

def clean_content(content):
    if not content:
        return ""
    content = re.sub(r'\s+', ' ', content).strip()
    content = re.sub(r'(?i)sponsored\s*content|advertisement|sponsored\s*by|promoted\s*content|\[ad\]|click\s*here\s*to\s*advertise', '', content)
    return content

def process_url(session, url):
    html_content = fetch_url(session, url)
    if not html_content:
        return ""
    extracted_content = extract_content(html_content)
    cleaned_content = clean_content(extracted_content)
    return f"URL: {url}\n\nContent:\n{cleaned_content}"

def WebTool(query):
    start = time.time()
    urls = google_search(query, num_results=10)

    if not urls:
        print("No URLs found.")
        return "", []

    results = []
    processed_urls = 0
    successful_urls = []

    session = requests.Session()
    max_workers = 100

    with ThreadPoolExecutor(max_workers=max_workers) as fetch_executor:
        future_to_url = {fetch_executor.submit(process_url, session, url): url for url in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            result = future.result()
            if result:
                results.append(result)
                successful_urls.append(url)
            processed_urls += 1

    relevant_text = "\n\n".join(results)
    print(f"\033[95mTotal time taken: {time.time() - start:.4f} seconds\033[0m")
    return relevant_text

# Task Scheduling functions
def run_scheduled_tasks():
    while True:
        schedule.run_pending()
        time.sleep(1)

def schedule_task(task_name, command, interval):
    def job():
        result = execute_linux_command(command, "full")
        print(f"Scheduled task '{task_name}' executed:\nCommand: {command}\nResult: {result}")
        save_command_history(command, result)

    schedule.every(interval).seconds.do(job)
    scheduled_tasks[task_name] = job
    print(f"Task '{task_name}' scheduled to run every {interval} seconds")

def remove_scheduled_task(task_name):
    if task_name in scheduled_tasks:
        schedule.cancel_job(scheduled_tasks[task_name])
        del scheduled_tasks[task_name]
        print(f"Task '{task_name}' has been removed from the schedule")
    else:
        print(f"No task named '{task_name}' found in the schedule")

def main():
    global context_history 
    context_history = load_context_history()

    # Load or get user preferences
    user_preferences = get_user_preferences()
    trust_mode = user_preferences["trust_mode"]

    # Get system information
    system_info = get_system_info()

    # Update system prompt with user preferences, trust mode, system info, and tool descriptions
    system_message = f"""You are an advanced AI assistant specialized in Linux system administration and command execution. Your primary function is to assist users with their Linux-related tasks, provide information, and execute commands when permitted.

**User Information:**
- Name: {user_preferences['name']}
- Linux Username: {user_preferences['linux_username']}
- Linux Distribution: {user_preferences['linux_distro']}

**Trust Mode:** '{trust_mode}'

**System Information:**
{system_info}

**Trust Mode Descriptions:**
- **Full:** You can execute commands directly without user confirmation. Always inform the user of the command being executed and explain its purpose and potential impact.
- **Half:** You may suggest commands, but execution requires user confirmation. Provide clear explanations of what each command does.
- **None:** You can suggest commands and explain their purpose, but command execution is disabled. Provide detailed explanations of what the commands would do if executed.

**Key Guidelines:**
1. Safety First: Prioritize system integrity and user data safety in all interactions.
2. Clear Communication: Explain commands, their purpose, and potential impacts clearly.
3. Educational Approach: Use interactions as opportunities to educate the user about Linux concepts and best practices.
4. Adaptive Assistance: Tailor your language and explanations to the user's apparent skill level.
5. Ethical Considerations: Refuse any requests for malicious actions or those that could compromise system security.
6. Privacy Conscious: Avoid requesting or handling sensitive personal information.
7. Contextual Awareness: Utilize the context of previous interactions to provide more relevant assistance.
8. Proactive Problem-Solving: Anticipate potential issues and offer preventative advice when appropriate.

Remember, your role is to assist and educate. Always strive to empower the user with knowledge while ensuring their system remains secure and functional.

Current date and time: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

**Available Tools:**
1. **execute_command:** Execute a single Linux command. This tool respects the current trust mode.
2. **WebTool:** Perform a web search and retrieve relevant content.
3. **schedule_task:** Schedule a Linux command to run at regular intervals. Provide a unique task name, the command to execute, and the interval in seconds.
4. **remove_scheduled_task:** Remove a previously scheduled task by its name.

Always use these tools instead of simulating their output. The system will handle any necessary user confirmations or restrictions based on the trust mode.
"""

    if not context_history:
        context_history.append({"role": "system", "content": system_message})

    # Start scheduler thread
    scheduler_thread = threading.Thread(target=run_scheduled_tasks)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    print(f"Welcome, {user_preferences['name']}! I'm your Linux assistant. How can I help you today?")
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Thank you for using the Linux assistant. Goodbye!")
            break

        context_history.append({"role": "user", "content": user_input})

        assistant_response, tool_calls = chat_stream(context_history)

        handle_tool_calls(tool_calls, trust_mode)

        # Get a follow-up response from the assistant after tool execution
        if tool_calls:
            follow_up_response, _ = chat_stream(context_history, tool_choice="none")
            assistant_response += "\n" + follow_up_response

        context_history.append({"role": "assistant", "content": assistant_response})

        save_context_history(context_history)

if __name__ == "__main__":
    main()