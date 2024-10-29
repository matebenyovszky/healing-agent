# Healing Agent 🩺

Healing Agent is an intelligent code assistant that automatically detects and fixes errors in your Python code. It leverages the power of AI to provide smart suggestions and corrections, helping you write more robust and error-free code.

## Table of Contents 📚

- [Features](#features-✨)
- [Installation](#installation-💻)
- [Usage](#usage-🔧)
- [Configuration](#configuration-⚙️)
- [Testing](#testing-🧪)
- [Use Cases](#use-cases-💡)
- [Contributing](#contributing-🤝)
- [License](#license-📜)

## Features ✨

- 🚨 Automatic error detection: Healing Agent monitors your code execution and catches any exceptions or errors that occur.
- 🔍 Intelligent code analysis: It analyzes the error details, including the exception type, error message, and traceback, to understand the root cause of the issue.
- 🧠 AI-powered (LLM) code healing: Healing Agent uses advanced AI algorithms to generate code fixes and suggestions based on the error context and best practices.
- 🔧 Seamless integration: It integrates seamlessly with your existing Python projects, requiring minimal setup and configuration.

## Installation 💻

To install Healing Agent, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/matebenyovszky/healing-agent.git
   ```

2. Navigate to the project directory:
   ```bash
   cd healing-agent
   ```

3. Install:
   ```bash
   pip install -e .
   ```

## Usage 🔧

To use Healing Agent in your project, follow these steps:

1. Import the `healing_agent` decorator in your Python file:
   ```python
   from healing_agent.healing_agent import healing_agent
   ```

2. Decorate the function you want to monitor with `@healing_agent`:
   ```python
   @healing_agent
   def your_function():
       # Your code here
   ```

3. Run your Python script as usual. Healing Agent will automatically detect and attempt to fix any errors that occur within the decorated function.

## Configuration ⚙️

Healing Agent can be configured to suit your needs. It uses `healing_agent_config.py` to set the AI provider and associated API keys. It automatically loads the configuration from `healing_agent_config.py` if it exists, otherwise it will use the default configuration. It copies the default configuration to `healing_agent_config.py` if it doesn't exist to your default configuration directory.

## Testing 🧪

To test Healing Agent, you can use the `scripts/test_file_generator.py` script to generate test files in the `tests` directory. `overall_test.py` will run all tests and provide a report on the functionality of Healing Agent.

## Use Cases 💡

- **Development**: Use Healing Agent during development to catch and fix errors early.
- **Production Monitoring**: Integrate Healing Agent into your production environment to monitor and automatically fix errors in real-time.
- **Educational Tool**: Use Healing Agent as a learning tool to understand common coding errors and how to fix them.

Not intended for production use.

## Contributing 🤝

We welcome contributions from the community! To contribute:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature/YourFeature`).
3. Commit your changes (`git commit -m 'Add some feature'`).
4. Push to the branch (`git push origin feature/YourFeature`).
5. Open a pull request.

## License 📜

Healing Agent is distributed under the MIT License. See `LICENSE` for more information.