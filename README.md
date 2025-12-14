# ECE30816-Fall2025-Team28
Team project repository for ECE30861 Software Engineering

## Team Members
- Josh LeBlanc
- Herbert de Bruyn
- James Neff
- Dylan Brannick

## Project Overview
This project is a Python application that fetches and analyzes model information from Hugging Face, including associated datasets and GitHub repositories. It provides a comprehensive view of machine learning models, their metadata, and related resources.

## Features
- Fetch model information from Hugging Face Hub
- Download and parse model README files
- Retrieve associated dataset information
- Analyze GitHub repository metadata, contributors, and commit history
- Support for multiple data sources integration
- **AI-Powered Analysis**: Generate comprehensive model analysis using Google Gemini API
- **Custom Prompt Templates**: Pre-built templates for model analysis, dataset summarization, and code review
- **Flexible LLM Integration**: Easy-to-use service for AI-powered insights and summaries

## Prerequisites
- Python 3.12 or higher
- Git
- Hugging Face account (for API access)
- GitHub account (for API access, optional but recommended)
- **Google Cloud Account** (for Gemini API access, optional but recommended for AI features)

## Setup Instructions

### 1. Set Up Python Virtual Environment
This project uses a virtual environment with files directly in the root directory.

#### On Windows:
```powershell
# The virtual environment is already set up in the repository
# Verify Python version
./bin/python.exe --version
```

#### On macOS/Linux:
```bash
# The virtual environment is already set up in the repository
# Verify Python version
./bin/python --version
```

### 2. Install Dependencies
Dependencies should already be installed in the virtual environment, but if you need to reinstall:

```bash
# Windows
./bin/python.exe -m pip install -r requirements.txt

# macOS/Linux
./bin/python -m pip install -r requirements.txt
```

### 3. Environment Variables Setup
Create a `.env` file in the project root directory with the following variables:

```env
# Required: Hugging Face API token
HF_TOKEN=your_hugging_face_token_here

# Optional: GitHub Personal Access Token (for enhanced API limits)
GITHUB_TOKEN=your_github_token_here
```

#### Getting API Tokens:

**Hugging Face Token (Required):**
1. Go to [Hugging Face Settings](https://huggingface.co/settings/tokens)
2. Click "New token"
3. Choose "Read" permissions
4. Copy the token and add it to your `.env` file

**GitHub Token (Optional):**
1. Go to [GitHub Settings > Personal Access Tokens](https://github.com/settings/tokens)
2. Click "Generate new token (classic)"
3. Select scopes: `public_repo`, `read:user`
4. Copy the token and add it to your `.env` file

### 5. VS Code Configuration
If using VS Code, the project includes configuration files in `.vscode/`:
- `settings.json`: Python interpreter and analysis settings
- `launch.json`: Debug configurations

Ensure VS Code uses the correct Python interpreter:
1. Open VS Code in the project directory
2. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
3. Type "Python: Select Interpreter"
4. Choose `./bin/python.exe` (Windows) or `./bin/python` (macOS/Linux)

## Project Structure
```
.
├── src/
│   ├── main.py                 # Main application entry point
│   ├── Controllers/
│   │   └── ModelFetcher.py     # Main controller for fetching model data
│   ├── Services/
│   │   ├── Request_Service.py  # HTTP requests and API interactions
│   │   └── LLM_Service.py      # Language model services
│   ├── Models/
│   │   └── Model.py            # Data models and structures
│   ├── Commands/
│   │   └── Cli.py              # Command-line interface
│   └── Testing/
│       └── test_basic.py       # Unit tests
├── bin/                        # Virtual environment executables
├── lib/                        # Python packages
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (create this)
└── README.md                   # This file
```

## Usage

### Running the Application
```bash
# Windows
cd "path/to/ECE30816-Fall2025-Team28"
./bin/python.exe -m src.main

# macOS/Linux
cd path/to/ECE30816-Fall2025-Team28
./bin/python -m src.main
```

### Running Tests
```bash
# Windows
./bin/python.exe -m pytest src/Testing/

# macOS/Linux
./bin/python -m pytest src/Testing/
```

### AI-Powered Analysis (LLM Service)

The project includes an advanced LLM service that integrates with Google's Gemini API to provide intelligent analysis of models, datasets, and code repositories.

#### Features:
- **Model Analysis**: Comprehensive AI-powered analysis of machine learning models
- **Dataset Summarization**: Intelligent summaries of datasets and their characteristics  
- **Code Review**: Automated code repository analysis and recommendations
- **Custom Prompts**: Flexible prompt preparation system with templates
- **REST API Integration**: Direct integration with Gemini API without heavy dependencies

#### Available Templates:
1. **model_analysis**: Analyzes ML models including purpose, methodology, and recommendations
2. **dataset_summary**: Provides concise summaries of datasets and their applications
3. **code_review**: Reviews code repositories with constructive feedback

#### Configuration:
Add your Gemini API key to the `.env` file:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Get your API key from:
- [Google AI Studio](https://aistudio.google.com/app/apikey) (Recommended)
- [Google Cloud Console](https://console.cloud.google.com/apis/credentials) (Advanced users)

### Example Usage
The application currently demonstrates fetching information for the OpenCUA-32B model:
- Model: `https://huggingface.co/xlangai/OpenCUA-32B`
- Associated datasets from Hugging Face
- GitHub repository analysis

## Development

### Adding New Features
1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Make your changes in the appropriate modules
3. Add tests in the `Testing/` directory
4. Update documentation as needed
5. Create a pull request

### Code Structure Guidelines
- Controllers: Handle business logic and orchestration
- Services: Handle external API calls and data processing
- Models: Define data structures and models
- Commands: Handle CLI interactions

## Troubleshooting

### Common Issues

**Import Errors:**
- Ensure you're running the application with `-m src.main` from the project root
- Verify the virtual environment is active and contains all dependencies

**API Authentication Errors:**
- Check that your `.env` file exists and contains valid tokens
- Verify token permissions on Hugging Face and GitHub

**Permission Errors:**
- On Windows: Use PowerShell or Command Prompt as Administrator if needed
- On macOS/Linux: Ensure execute permissions on `./bin/python`

### Getting Help
1. Check the GitHub Issues for known problems
2. Contact team members via the course communication channels
3. Refer to the API documentation:
   - [Hugging Face Hub Python Library](https://huggingface.co/docs/huggingface_hub/index)
   - [GitHub API Documentation](https://docs.github.com/en/rest)

## Contributing
1. Follow the existing code style and structure
2. Add appropriate type hints and documentation
3. Include tests for new functionality
4. Update the README if adding new setup requirements

## License
This is a course project for ECE30816 Software Engineering at Purdue University.
