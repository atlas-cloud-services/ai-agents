# Setup Guide

This guide details how to set up the ACS-AI-AGENTS development environment.

*(This section can expand on the README's setup instructions with more detail if needed, e.g., specific Python versions, troubleshooting tips)*

## Prerequisites

*   Python 3.10 or higher
*   `git`
*   Access to the GitHub repository

## Installation Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/atlas-cloud-services/ACS-AI-AGENTS.git
    cd ACS-AI-AGENTS
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate # On Windows: venv\Scripts\activate
    ```
3.  **Install dependencies (including development/testing tools):**
    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    ```
4.  **Install project in editable mode:**
    ```bash
    pip install -e .
    ```
    *This allows Python and tools like pytest to correctly find project modules.* 