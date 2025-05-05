# Testing Strategy

This document outlines the testing approach for the ACS-AI-AGENTS project.

## Test Categories

We categorize tests to ensure different levels of coverage and feedback speed:

1.  **Unit Tests (`@pytest.mark.unit`):**
    *   **Purpose:** Verify the correctness of individual functions, methods, or classes in isolation.
    *   **Scope:** Focused on a single module or small set of related functions.
    *   **Dependencies:** External dependencies (like databases, network calls, LLM services) are typically mocked.
    *   **Speed:** Very fast.
    *   **Location:** Usually within a `tests/` subdirectory alongside the code being tested (e.g., `agents/incident/tests/`).

2.  **Integration Tests (`@pytest.mark.integration`):**
    *   **Purpose:** Verify the interaction and communication between different components of the system (e.g., Incident Agent talking to LLM Service, MCP routing messages).
    *   **Scope:** Involves multiple components, often running together (e.g., via `docker-compose`).
    *   **Dependencies:** May involve real running dependencies (like a test database, Redis) or containerized services. External third-party APIs might still be mocked.
    *   **Speed:** Slower than unit tests.
    *   **Location:** Potentially in a dedicated top-level `integration_tests/` directory.
    *   *(Note: Currently, dedicated integration tests need to be added.)*

3.  **End-to-End (E2E) Tests (`@pytest.mark.e2e`):**
    *   **Purpose:** Simulate realistic user workflows from start to finish, verifying the entire system behavior.
    *   **Scope:** Covers the complete flow through multiple services, potentially including UI interactions if applicable.
    *   **Dependencies:** Ideally uses a deployed-like environment with all necessary services running.
    *   **Speed:** Slowest test category.
    *   **Location:** Potentially in a dedicated top-level `e2e_tests/` directory.
    *   *(Note: Currently, dedicated E2E tests need to be added.)*

## Running Tests Locally

A test runner script (`run_tests.sh`) is provided for convenience.

**Prerequisites:**

*   Python environment set up with dependencies installed (`pip install -r requirements.txt`).
*   (For Integration/E2E tests) Docker and Docker Compose might be required if tests rely on running services.

**Usage:**

```bash
# Show help
./run_tests.sh --help

# Run only unit tests
./run_tests.sh --unit

# Run only integration tests
./run_tests.sh --integration

# Run only E2E tests
./run_tests.sh --e2e

# Run multiple categories (unit and integration)
./run_tests.sh --unit --integration

# Run all tests
./run_tests.sh --all
```

The script executes `pytest` with the appropriate markers (`-m "unit or ..."`) and generates raw Allure results in the `./allure-results` directory.

## Allure Reporting

We use Allure Framework for rich test reports.

**Generating & Viewing the Report Locally:**

1.  **Run tests:** Execute `./run_tests.sh` with the desired categories. This creates `./allure-results`.
2.  **Install Allure Commandline:** If you don't have it, follow the installation instructions at [docs.qameta.io/allure/](https://docs.qameta.io/allure/#_installing_a_commandline).
3.  **Generate HTML report:**
    ```bash
    allure generate ./allure-results --clean -o ./allure-report
    ```
    *   `--clean` removes previous report data.
    *   `-o ./allure-report` specifies the output directory for the HTML report.
4.  **Open the report:**
    ```bash
    allure open ./allure-report
    ```
    This should open the interactive report in your web browser.

**Interpreting the Report:**

*   **Overview:** Shows overall statistics, trends, and environment details.
*   **Categories:** Custom groupings of test failures (can be configured).
*   **Suites:** Test results grouped by file/class structure.
*   **Graphs:** Visualizations of severity, duration, status, etc.
*   **Timeline:** Shows parallel execution and timing.
*   **Behaviors:** Tests grouped by Feature and Story (based on decorators).
*   **Packages:** Tests grouped by code package structure.

Click on individual tests to see details, steps (if used), fixtures, logs, and attachments (if added).

## Writing New Tests

*   **File/Function Naming:** Follow standard `pytest` conventions (`test_*.py`, `test_*` functions).
*   **Location:** Place unit tests alongside the code under test (e.g., `agents/incident/tests/`). Place integration/E2E tests in dedicated top-level directories.
*   **Markers:** Add the appropriate category marker (`@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`).
*   **Allure Decorators:**
    *   Add `@allure.feature("Descriptive Feature Name")`.
    *   Add `@allure.story("Specific User Story or Scenario")`.
    *   Add `@allure.severity(allure.severity_level.NORMAL)` (or `MINOR`, `CRITICAL`, `BLOCKER`).
    *   *(Optional)* Use `@allure.step("Doing something...")` within test functions for more granular reporting.
    *   *(Optional)* Use `allure.attach(...)` to add data (like logs, request/response data) to the report, especially on failure.
*   **Fixtures:** Use `pytest` fixtures for setup/teardown (e.g., creating test data, mocking dependencies, setting up DB connections). 