# Development Workflow

This page outlines the recommended development practices for the ACS-AI-AGENTS project.

## Branching Strategy

We use a Gitflow-like branching model:

*   **`main`**: Represents production-ready code. Direct commits are forbidden.
*   **`dev`**: The main integration branch for ongoing development. Features are merged here before potentially going to `main`.
*   **`feature/<jira>-<short-description>`**: Branched from `dev` for developing new features (e.g., `feature/AI-124-add-caching`). Merged back into `dev` via Pull Request.
*   **`hotfix/<jira>-<short-description>`**: Branched from `main` for critical production bug fixes. Merged into both `main` and `dev`.
*   **`bugfix/<jira>-<short-description>`**: Branched from `dev` for fixing non-critical bugs found during development. Merged back into `dev`.

## Commits

Follow the conventional commit format:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

*   **Types:** `feat`, `fix`, `build`, `chore`, `ci`, `docs`, `style`, `refactor`, `perf`, `test`.
*   **Scope:** Optional, indicates the part of the codebase affected (e.g., `llm-service`, `incident-agent`, `docs`).
*   **Example:** `feat(incident-agent): Add confidence scoring logic`
*   Reference Jira tickets in the body or footer (e.g., `Refs: AI-123`).

## Testing

*   Test-Driven Development (TDD) is encouraged where practical.
*   Write unit tests using `pytest` for individual functions and classes.
*   Write integration/end-to-end (E2E) tests using `pytest` and `httpx` (with `pytest-httpx` for mocking) to test API endpoints and interactions between components (while mocking external services like the LLM).
*   Place tests in a `tests/` subdirectory within the component being tested (e.g., `agents/incident/tests/`).
*   Use separate files for unit tests (e.g., `test_analyzer.py`) and E2E tests (e.g., `test_incident_agent_e2e.py`).
*   Ensure tests cover core logic, edge cases, and error handling.
*   Run all tests from the project root directory:
    ```bash
    pytest
    ```
*   Run tests for a specific component or file:
    ```bash
    pytest agents/incident/
    pytest tests/test_incident_agent_e2e.py
    ```

## Pull Requests (PRs)

*   Create PRs from `feature/*` or `bugfix/*` branches targeting `dev`.
*   Create PRs from `hotfix/*` branches targeting `main` (and subsequently merge to `dev`).
*   Use clear titles referencing the Jira ticket (e.g., `[AI-123] feat(incident-agent): Implement analysis caching`).
*   Provide a summary of changes and link to the Jira ticket.
*   Ensure tests pass in CI (when implemented).
*   Require at least one approval before merging.

## Code Style

*   Follow PEP 8 guidelines.
*   Use type hints consistently.
*   Write clear docstrings (Google style recommended) for modules, classes, and functions.
*   Use linters (e.g., Flake8, Black, isort) - configuration to be added. 