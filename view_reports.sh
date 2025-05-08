#!/bin/bash

# Download the latest test results artifact if available
if [ "$1" == "--download" ]; then
  echo "Downloading latest test results from GitHub Actions..."
  # This requires the GitHub CLI to be installed
  # Install it with: brew install gh (on macOS) or https://cli.github.com/
  if command -v gh &> /dev/null; then
    # Authenticate with GitHub if needed
    # gh auth status || gh auth login # Removing interactive login for script
    echo "Please ensure you are authenticated with GitHub CLI (gh auth login)"
    
    # Clean old results before downloading
    echo "Cleaning old results directory..."
    rm -rf allure-results
    
    # Download the latest artifact from the main/dev branch (adjust as needed)
    echo "Attempting to download 'test-results' artifact..."
    # You might need to adjust the workflow name or branch if needed
    gh run download --name test-results --repo "$GITHUB_REPOSITORY" # Assuming GITHUB_REPOSITORY is set or replace with owner/repo
    
    if [ $? -eq 0 ]; then
        echo "Downloaded test results to allure-results/"
    else
        echo "Failed to download artifact. Did the workflow run? Does the artifact exist?"
        # Optional: List recent runs to help debugging
        # gh run list --limit 5
        exit 1
    fi
  else
    echo "GitHub CLI (gh) not found. Please install it to download artifacts." >> /dev/stderr
    exit 1
  fi
fi

# Generate and view Allure report
if [ -d "allure-results" ]; then
  echo "Generating Allure report..."
  
  # Check if allure is installed
  if ! command -v allure &> /dev/null; then
    echo "Allure command line not found. Attempting to install..." >&2
    
    # Try to install Allure based on the OS
    INSTALL_CMD=""
    if [[ "$OSTYPE" == "darwin"* ]]; then
      # macOS
      if command -v brew &> /dev/null; then
          INSTALL_CMD="brew install allure"
      else
          echo "Homebrew not found. Please install Allure manually or install Homebrew." >&2
          exit 1
      fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
       # Basic check for apt (Debian/Ubuntu)
       if command -v apt-get &> /dev/null; then
           # Requires sudo, might ask for password
           echo "Attempting install via apt (may require sudo password)..." >&2
           INSTALL_CMD="sudo apt-get update && sudo apt-get install -y allure"
       else 
           echo "apt not found. Cannot automatically install Allure on this Linux distribution." >&2
           echo "Please install Allure manually: https://docs.qameta.io/allure/#_installing_a_commandline" >&2
           exit 1
       fi
    else
      echo "Unsupported OS for automatic install. Please install Allure manually: https://docs.qameta.io/allure/#_installing_a_commandline" >&2
      exit 1
    fi

    # Execute install command
    eval $INSTALL_CMD
    if [ $? -ne 0 ]; then
        echo "Allure installation failed." >&2
        exit 1
    fi
    # Verify installation
    if ! command -v allure &> /dev/null; then
        echo "Allure still not found after installation attempt." >&2
        exit 1
    fi
  fi
  
  allure generate allure-results --clean -o allure-report
  if [ $? -eq 0 ]; then
      allure open allure-report
  else
      echo "Allure report generation failed." >&2
      exit 1
  fi
else
  echo "No allure-results directory found." >&2
  echo "Run tests first (e.g., ./run_tests.sh --unit) or download results (./view_reports.sh --download)." >&2
  exit 1
fi 