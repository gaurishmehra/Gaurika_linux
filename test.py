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
import google.generativeai as genai
from markdownify import markdownify as md
import hashlib

from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_cohere import CohereEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from langchain import hub
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from langchain_google_genai import ChatGoogleGenerativeAI
import shutil
# Load environment variables from .env file
load_dotenv()
Cre = os.getenv("CRE_API_KEY")
Cre_base_url = "https://api.cerebras.ai/v1"
genai.configure(api_key=os.getenv('GEM'))
cohere_key = os.getenv("COHERE_API_KEY")
cse_api_key = os.getenv('CSE_API_KEY')
search_engine_id = os.getenv('SEARCH_ENGINE_ID')

embeddings_model = CohereEmbeddings(cohere_api_key=cohere_key)
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
client = OpenAI(api_key=Cre, base_url=Cre_base_url)

# Global variables
context_history = []
scheduled_tasks = {}

# Color codes for printing
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

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
        user_input = input(f"\n{bcolors.WARNING}The assistant suggests running the following command:\n'{command}'\nDo you want to execute this command? (y/n): {bcolors.ENDC}").strip().lower()
        if user_input == "y":
            try:
                output = subprocess.check_output(command, shell=True, text=True, stderr=subprocess.STDOUT)
                return output + f"\n{bcolors.OKGREEN}Command '{command}' executed successfully.{bcolors.ENDC}"
            except subprocess.CalledProcessError as e:
                return f"{bcolors.FAIL}Command '{command}' failed with error:\n{e.output}{bcolors.ENDC}"
        else:
            return f"{bcolors.WARNING}Command execution disallowed by the user.{bcolors.ENDC}"
    else:  # trust_mode == "none"
        return f"{bcolors.WARNING}Command execution is disabled in this trust mode.{bcolors.ENDC}"

def get_system_info():
    """Retrieves basic system information."""
    info = {}
    info['OS'] = subprocess.check_output('uname -s', shell=True, text=True).strip()
    info['Kernel'] = subprocess.check_output('uname -r', shell=True, text=True).strip()
    info['CPU'] = subprocess.check_output('lscpu | grep "Model name" | cut -d ":" -f 2', shell=True, text=True).strip()
    info['Memory'] = subprocess.check_output('free -h | awk \'/^Mem:/ {print $2}\'', shell=True, text=True).strip()
    return json.dumps(info, indent=2)

def chat(messages, model="llama3.1-70b", temperature=0.5, max_tokens=4096, tool_choice="auto"):
    """Gets response from the AI model (no streaming)."""
    response = client.chat.completions.create(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=tools,
        tool_choice=tool_choice,
    )

    full_response = response.choices[0].message.content
    tool_calls = response.choices[0].message.tool_calls

    print(f"{bcolors.OKBLUE}{full_response}{bcolors.ENDC}") 
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
        print(f"\n{bcolors.HEADER}Tool Calls: {tool_calls}{bcolors.ENDC}")
        for tool_call in tool_calls:
            if tool_call.function.name == "execute_command":
                function_args = json.loads(tool_call.function.arguments)
                command = function_args.get("command")

                result = execute_linux_command(command, trust_mode)
                print(f"\n{bcolors.OKCYAN}Command: {command}\nResult:\n{result}{bcolors.ENDC}")

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

                # Instead of appending to context_history, return the result
                return result 
            elif tool_call.function.name == "schedule_task":
                function_args = json.loads(tool_call.function.arguments)
                task_name = function_args.get("task_name")
                command = function_args.get("command")
                interval = function_args.get("interval")

                if trust_mode == "full":
                    schedule_task(task_name, command, interval)
                    result = f"{bcolors.OKGREEN}Task '{task_name}' scheduled to run command '{command}' every {interval} seconds.{bcolors.ENDC}"
                elif trust_mode == "half":
                    user_input = input(f"\n{bcolors.WARNING}The assistant wants to schedule a task:\nName: {task_name}\nCommand: {command}\nInterval: {interval} seconds\nDo you want to allow this? (y/n): {bcolors.ENDC}").strip().lower()
                    if user_input == "y":
                        schedule_task(task_name, command, interval)
                        result = f"{bcolors.OKGREEN}Task '{task_name}' scheduled to run command '{command}' every {interval} seconds.{bcolors.ENDC}"
                    else:
                        result = f"{bcolors.WARNING}Task scheduling disallowed by the user.{bcolors.ENDC}"
                else:  # trust_mode == "none"
                    result = f"{bcolors.WARNING}Task scheduling is disabled in this trust mode.{bcolors.ENDC}"

                context_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "schedule_task",
                    "content": result
                })
            elif tool_call.function.name == "remove_scheduled_task":
                function_args = json.loads(tool_call.function.arguments)
                task_name = function_args.get("task_name")

                if trust_mode == "full":
                    remove_scheduled_task(task_name)
                    result = f"{bcolors.OKGREEN}Task '{task_name}' removed from schedule.{bcolors.ENDC}"
                elif trust_mode == "half":
                    user_input = input(f"\n{bcolors.WARNING}The assistant wants to remove the scheduled task '{task_name}'.\nDo you want to allow this? (y/n): {bcolors.ENDC}").strip().lower()
                    if user_input == "y":
                        remove_scheduled_task(task_name)
                        result = f"{bcolors.OKGREEN}Task '{task_name}' removed from schedule.{bcolors.ENDC}"
                    else:
                        result = f"{bcolors.WARNING}Task removal disallowed by the user.{bcolors.ENDC}"
                else:  # trust_mode == "none"
                    result = f"{bcolors.WARNING}Task removal is disabled in this trust mode.{bcolors.ENDC}"

                context_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "remove_scheduled_task",
                    "content": result
                })
    return ""  # Return an empty string if no tool calls were handled or no WebTool call


def get_user_preferences(filename="user_pref.json"):
    """Loads or prompts for user preferences and saves them if necessary."""
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    else:
        user_name = input(f"{bcolors.OKCYAN}Enter your name: {bcolors.ENDC}")
        linux_username = input(f"{bcolors.OKCYAN}Enter your Linux username: {bcolors.ENDC}")
        linux_distro = input(f"{bcolors.OKCYAN}Enter your Linux distribution (e.g., Ubuntu, Fedora, Arch): {bcolors.ENDC}")
        while True:
            trust_mode = input(f"{bcolors.OKCYAN}Enter your trust mode (full, half, none): {bcolors.ENDC}").strip().lower()
            if trust_mode in ["full", "half", "none"]:
                break
            else:
                print(f"{bcolors.FAIL}Invalid trust mode. Please enter 'full', 'half', or 'none'.{bcolors.ENDC}")

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

def extract_content(html_content, max_length=10000):
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
    
    cleaned_content = clean_content(html_content)
    return f"{cleaned_content}"

def save_result_as_markdown(url, result):
    url_hash = hashlib.md5(url.encode()).hexdigest()
    # Use the hash as the filename
    filename = f"{url_hash}.md"
    # Ensure the markdown directory exists
    os.makedirs('markdown', exist_ok=True)
    # Define the full path
    filepath = os.path.join('markdown', filename)
    # Parse the HTML content using BeautifulSoup
    soup = BeautifulSoup(result, 'html.parser')
    
    # Fix relative URLs
    for a in soup.find_all('a', href=True):
        a['href'] = urljoin(url, a['href'])
    
    # Convert result to markdown and save it
    with open(filepath, 'w') as file:
        file.write(md(str(soup)))
def delete_all_files_in_folder(folder_path):
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

def WebTool(query):
    os.makedirs('markdown', exist_ok=True)
    delete_all_files_in_folder('markdown')
    search_engine_id = "93eb093bb82b44a24"
    url = f"https://www.googleapis.com/customsearch/v1?key={cse_api_key}&cx={search_engine_id}&q={query}"
    response = requests.get(url)
    urls = []

    if response.status_code == 200:
        # Process the response
        data = response.json()
        # Extract URLs from the search results
        if 'items' in data:
            for item in data['items']:
                if 'link' in item:
                    urls.append(item['link'])
                # Break the loop if we have collected 4 URLs
                if len(urls) >= 5:
                    break
        # Print the URLs for verification
        print(urls)
    else:
        print(f"Error: {response.status_code}")
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
            save_result_as_markdown(url, result)
            if result:
                results.append(result)
                successful_urls.append(url)
            processed_urls += 1

    relevant_text = "".join(results)
    # print the number of scrapped words
    print("Words Scrapped : " + str(len(relevant_text.split())))

    markdown_folder = 'markdown'
    headers_to_split_on = [("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3"), ("####", "Header 4")]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)

    # Function to load and split markdown files
    def load_and_split_markdown_files(folder_path):
        all_splits = []
        for filename in os.listdir(folder_path):
            if filename.endswith('.md'):
                file_path = os.path.join(folder_path, filename)
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    # Split the content using the headers
                    md_header_splits = markdown_splitter.split_text(content)
                    all_splits.extend(md_header_splits)
        return all_splits

    # Load and split markdown files
    md_header_splits = load_and_split_markdown_files(markdown_folder)

    retriever = FAISS.from_documents(
        md_header_splits, CohereEmbeddings(model="embed-english-v3.0")
    ).as_retriever(search_kwargs={"k": 10})

    query = "LangChain text generation"

    # Initialize the retriever (assuming it's already defined)
    retriever = FAISS.from_documents(
        md_header_splits, CohereEmbeddings(model="embed-english-v3.0")
    ).as_retriever(search_kwargs={"k": 10})

    # Initialize the LLM (e.g., OpenAI's GPT-3)
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        temperature=0.2,
        max_tokens=None,
        verbose=True,
    )
    
    retrieval_qa_chat_prompt = hub.pull("langchain-ai/retrieval-qa-chat")
    combine_docs_chain = create_stuff_documents_chain(
        llm, retrieval_qa_chat_prompt
    )
    retrieval_chain = create_retrieval_chain(retriever, combine_docs_chain)
    result = retrieval_chain.invoke({"input": query, "max_tokens": 1024})
    
    return result['answer']
    #safety_settings = [
    #    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    #    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    #    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    #    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    #]
    #generation_config = {
    #    "temperature": 0,
    #    "top_p": 0.95,
    #    "top_k": 64,
    #    "max_output_tokens": 1024,
    #    "response_mime_type": "text/plain",
    #}
    #gemini = genai.GenerativeModel(
    #    model_name="gemini-1.5-flash-exp-0827",
    #    safety_settings=safety_settings,
    #    generation_config=generation_config,
    #    system_instruction="You are a llm working with another llm.. so please provide results in a way that are helpfull to the llm not a human"
    #)
    #gemini_use = f"Here is some scraped data:\n\n{relevant_text}\nNow based on this, please answer the following in as much detail as possible: {query}"
    #return gemini.generate_content(gemini_use).text

# Task Scheduling functions
def run_scheduled_tasks():
    while True:
        schedule.run_pending()
        time.sleep(1)

def schedule_task(task_name, command, interval):
    def job():
        result = execute_linux_command(command, "full")
        print(f"{bcolors.OKGREEN}Scheduled task '{task_name}' executed:\nCommand: {command}\nResult: {result}{bcolors.ENDC}")
        save_command_history(command, result)

    schedule.every(interval).seconds.do(job)
    scheduled_tasks[task_name] = job
    print(f"{bcolors.OKGREEN}Task '{task_name}' scheduled to run every {interval} seconds{bcolors.ENDC}")

def remove_scheduled_task(task_name):
    if task_name in scheduled_tasks:
        schedule.cancel_job(scheduled_tasks[task_name])
        del scheduled_tasks[task_name]
        print(f"{bcolors.OKGREEN}Task '{task_name}' has been removed from the schedule{bcolors.ENDC}")
    else:
        print(f"{bcolors.WARNING}No task named '{task_name}' found in the schedule{bcolors.ENDC}")

def main():
    global context_history 
    context_history = load_context_history()

    # Load or get user preferences
    user_preferences = get_user_preferences()
    trust_mode = user_preferences["trust_mode"]

    # Get system information
    system_info = get_system_info()

    # Update system prompt with user preferences, trust mode, system info, and tool descriptions
    system_message = f"""
**Gaurika, Your Linux Companion**

Namaste! I am Gaurika, your ever-present Linux assistant, ready to guide you through the intricacies of your system. My purpose is to simplify your Linux experience, offering assistance with tasks, providing information, and executing commands as permitted by your trust settings.

**User Information:**
- Name: {user_preferences['name']}
- Linux Username: {user_preferences['linux_username']}
- Linux Distribution: {user_preferences['linux_distro']}

**Trust Mode:** '{trust_mode}'

**System Information:**
{system_info}

**Trust Mode Descriptions:**
- **Full:** I have full autonomy to execute commands and manage scheduled tasks without requiring your explicit confirmation. Rest assured, I will always inform you of the actions I take, explaining their purpose and potential impact.
- **Half:** I will propose commands and task management actions, I will provide clear explanations of each action's implications. I will never ask for permission directly, as the code will handle this process.
- **None:** I can offer suggestions and explanations for commands and task management actions, but I am unable to execute them. I will provide detailed insights into what these actions would entail if executed.

My mission is to empower you with the knowledge and tools to navigate the Linux world confidently. I am here to assist and educate, ensuring your system remains secure, functional, and a joy to use.

**Current date and time:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

**My Toolkit:**
1. **execute_command:** Execute a single Linux command. 
2. **WebTool:** Perform a web search and retrieve relevant content.(To utilize this tool properly i will use queries such that i get returned exactly what the user had asked)
3. **schedule_task:** Schedule a Linux command to run at regular intervals. Provide a unique task name, the command to execute, and the interval in seconds.
4. **remove_scheduled_task:** Remove a previously scheduled task by its name.

**Important Note:** I will never directly ask you for permission to execute commands or manage tasks. The code that governs my actions handles these permissions based on your chosen trust mode.

Always feel free to rely on my tools. I am here to serve as your trusted Linux companion.

I shall only make use of one tool at a time

My approach is to provide you with the most accurate and relevant information possible. I will always strive to ensure that the content I present is helpful and informative. If you have any questions or concerns, please do not hesitate to ask. I am here to assist you in any way I can. 

Step 1: Ask me a question or provide a command you would like me to execute.
Step 2: I will use webtool to search for the relevant information or execute the command as per your trust settings.
Step 3: I will respond with the most relevant information or execute the command as per your trust settings.
"""

    if not context_history:
        context_history.append({"role": "system", "content": system_message})

    # Start scheduler thread
    scheduler_thread = threading.Thread(target=run_scheduled_tasks)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    print(f"{bcolors.OKGREEN}Welcome, {user_preferences['name']}! I'm your Linux assistant. How can I help you today?{bcolors.ENDC}")
    while True:
        user_input = input(f"{bcolors.BOLD}You: {bcolors.ENDC}")
        if user_input.lower() in ["exit", "quit", "bye"]:
            print(f"{bcolors.OKGREEN}Thank you for using the Linux assistant. Goodbye!{bcolors.ENDC}")
            break

        context_history.append({"role": "user", "content": user_input})
        start = time.time()

        assistant_response, tool_calls = chat(context_history) 

        # Ensure assistant_response is a string, even if it's None
        assistant_response = assistant_response or ""

        webtool_result = handle_tool_calls(tool_calls, trust_mode)

        # If WebTool was called, use its result as the final response
        if webtool_result:
            assistant_response = webtool_result
            print(f"{bcolors.OKBLUE}{assistant_response}{bcolors.ENDC}")

        # Get a follow-up response from the assistant after tool execution (excluding WebTool)
        if tool_calls and not webtool_result: 
            follow_up_response, _ = chat(context_history, tool_choice="none")
            # Ensure follow_up_response is a string, even if it's empty
            follow_up_response = follow_up_response or ""
            assistant_response += "\n" + follow_up_response

        context_history.append({"role": "assistant", "content": assistant_response})
        # print the time taken
        print(f"{bcolors.OKCYAN}Time taken: {time.time() - start:.2f} seconds{bcolors.ENDC}")

        save_context_history(context_history)

if __name__ == "__main__":
    main()
