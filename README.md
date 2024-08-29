# Gaurika: Your Linux Companion

Gaurika is an AI-powered Linux assistant designed to simplify your Linux experience. It can assist with tasks, provide information, execute commands (based on your trust settings), and even schedule tasks.

## Features

- **Command Execution:** Execute Linux commands with different trust modes (full, half, none).
- **Web Search:** Perform web searches and retrieve relevant content using the WebTool.
- **Task Scheduling:** Schedule Linux commands to run at regular intervals.
- **Contextual Awareness:** Remembers previous interactions for more relevant assistance.
- **System Information:** Provides basic system information (OS, kernel, CPU, memory).
- **User Preferences:** Stores user preferences (name, Linux username, distribution, trust mode).
- **Command History:** Logs executed commands and their outputs.
- **Color-Coded Output:** Makes the output more visually appealing and easier to understand.

## Trust Modes

Gaurika operates with three trust modes:

- **Full:** Gaurika has full autonomy to execute commands and manage scheduled tasks without requiring your confirmation.
- **Half:** Gaurika will propose commands and task management actions but will await your approval before proceeding.
- **None:** Gaurika can offer suggestions and explanations for commands and task management actions but cannot execute them.

## Getting Started

1. **Prerequisites:**
   - Python 3.8 or higher
   - cerebras API key
   - `dotenv` package (for managing environment variables)
   - `requests`, `selectolax`, `concurrent.futures`, `urllib.parse`, `collections`, `socket`, `openai`, `json`, `subprocess`, `datetime`, `schedule`, `threading` packages

2. **Installation:**
   - Clone this repository: `git clone https://github.com/gaurishmehra/gaurika.git`
   - Install the required packages: `pip install -r requirements.txt`
   - Create a `.env` file in the root directory and add your cerebras API key:
     ```
     cerebras_API_KEY=your_cerebras_api_key
     ```

3. **Running Gaurika:**
   - Run the `app.py` script: `python app.py` or `python3 app.py` depending on your Python installation.
   - Gaurika will prompt you for your name, Linux username, distribution, and trust mode if you haven't set them before.
   - Start interacting with Gaurika by typing your requests.

## Usage Examples

- **Execute a command:**
  - `execute_command: ls -l` (in full trust mode)
  - `Can you list the files in the current directory?` (Gaurika might suggest `ls -l` and ask for confirmation in half trust mode)
- **Perform a web search:**
  - `WebTool: hey.. what's up with the new llama 3.1 405b model?`
- **Schedule a task:**
  - `schedule_task: backup_files, cp -r /home/user/Documents /home/user/Backups, 3600` (schedule a backup every hour)
- **Remove a scheduled task:**
  - `remove_scheduled_task: backup_files`

## Disclaimer

Gaurika is a powerful tool, and it's important to use it responsibly. Be cautious when using the full trust mode, as Gaurika will have the ability to execute any command on your system. Always review the commands Gaurika suggests before approving them in half trust mode.

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests.

## License

This project is licensed under the MIT License.