# Gaurika: Your Intuitive Linux Companion

Gaurika is an AI-powered Linux assistant designed to make your Linux experience smoother and more enjoyable. Whether you're a seasoned Linux user or just starting out, Gaurika can help you with tasks, provide information, execute commands (with your permission), and even schedule tasks, all through a natural language interface. You can even choose to interact with Gaurika using your voice!

## Features

- **Command Execution:** Execute Linux commands easily. Gaurika offers three trust modes (full, half, none) to control how much autonomy you give it. 
- **Web Search:** Get answers to your questions quickly using the integrated WebTool, powered by the Cerebras API.
- **Task Scheduling:** Automate routine tasks by scheduling Linux commands to run at specific intervals.
- **Contextual Awareness:** Gaurika remembers your past interactions, allowing for more relevant and helpful responses.
- **System Information:** Get a quick overview of your system's specifications (OS, kernel, CPU, memory).
- **User Preferences:** Customize Gaurika by setting your preferred name, Linux username, distribution, trust mode, and interaction style (text or voice).
- **Command History:** Keep track of the commands you've executed and their outputs.
- **Color-Coded Output:** Enjoy a more visually appealing and easier-to-understand output.
- **Voice Interaction:** Communicate with Gaurika using your voice thanks to seamless integration with speech-to-text (powered by Groq) and text-to-speech engines.

## Trust Modes

Gaurika operates with three trust modes to ensure you're always in control:

- **Full:** Gaurika has full autonomy to execute commands and manage scheduled tasks without requiring your confirmation. Use with caution!
- **Half:** Gaurika will suggest commands and task management actions but will always ask for your approval before proceeding.
- **None:** Gaurika can offer suggestions and explanations for commands and task management actions but cannot execute them. Perfect for learning or when you want to be extra careful.

## Getting Started

1. **Prerequisites:**
   - Python 3.8 or higher
   - **Cerebras API key** (get yours at [Cerebras website] - for main inference)
   - **Groq API key** (get yours at [Groq website] - only needed for voice interaction)
   - **Gemini API key** (for RAG functionality in the WebTool)
   - Required Python packages: `dotenv`, `requests`, `selectolax`, `concurrent.futures`, `urllib.parse`, `collections`, `socket`, `openai`, `json`, `subprocess`, `datetime`, `schedule`, `threading`, `speech_recognition`, `pyttsx3`

2. **Installation:**
   - Clone this repository: `git clone https://github.com/gaurishmehra/Gaurika_linux.git`
   - Install the required packages manually (there is no requirements.txt file)
   - Create a `.env` file in the root directory and add your API keys:
     ```
     CEREBRAS_API_KEY=your_cerebras_api_key
     GROQ_API_KEY=your_groq_api_key (if using voice interaction)
     GEMINI_API_KEY=your_gemini_api_key
     ```

3. **Running Gaurika:**
   - Run the `app.py` script: `python app.py` or `python3 app.py` depending on your Python installation.
   - Gaurika will greet you and guide you through setting up your preferences (name, Linux username, distribution, trust mode, interaction style).
   - Start interacting with Gaurika by typing your requests or speaking to it!

## Usage Examples

**Text Interaction:**

- **Execute a command:**
  - `execute_command: ls -l` (in full trust mode)
  - `Can you list the files in the current directory?` (Gaurika might suggest `ls -l` and ask for confirmation in half trust mode)
- **Perform a web search:**
  - `WebTool: What's new in the latest Linux kernel release?`
- **Schedule a task:**
  - `schedule_task: backup_files, cp -r /home/user/Documents /home/user/Backups, 3600` (schedule a backup every hour)
- **Remove a scheduled task:**
  - `remove_scheduled_task: backup_files`

**Voice Interaction:**

- **Execute a command:**
  - "Gaurika, can you list all the files in this folder?"
- **Perform a web search:** 
  - "Gaurika, search the web for information about the latest Python release."
- **Schedule a task:**
  - "Gaurika, schedule a task to clean up my downloads folder every week."

## Disclaimer

Gaurika is a powerful tool, and it's important to use it responsibly, especially in full trust mode. Always be mindful of the commands you execute or approve. 

## Project Information

- **Authors:** Gaurish Mehra and Gunit Kumar
- **Development Time:** This project was conceptualized and developed within a day, with most of the actual coding done in just a few hours.

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
