#!/bin/bash

# Basic test runner script

# --- Configuration ---
ALLURE_RESULTS_DIR="./allure-results"
PYTHON_CMD="python"
PYTEST_CMD="${PYTHON_CMD} -m pytest"

# --- Argument Parsing ---
RUN_UNIT=false
RUN_INTEGRATION=false
RUN_E2E=false
SHOW_HELP=false

if [ $# -eq 0 ]; then
    echo "Usage: $0 [--unit] [--integration] [--e2e] [--all] [--help]"
    echo "  Runs specified test categories and generates Allure results."
    echo "  At least one category flag or --all must be provided."
    exit 1
fi

for arg in "$@"
do
  case $arg in
    --unit)         RUN_UNIT=true; shift ;; 
    --integration)  RUN_INTEGRATION=true; shift ;; 
    --e2e)          RUN_E2E=true; shift ;; 
    --all)          RUN_UNIT=true; RUN_INTEGRATION=true; RUN_E2E=true; shift ;; 
    --help|-h)      SHOW_HELP=true; shift ;; 
    *)              echo "Unknown option: $arg"; exit 1 ;;
  esac
done

if [ "$SHOW_HELP" = true ] ; then
    echo "Usage: $0 [--unit] [--integration] [--e2e] [--all] [--help]"
    echo "  Runs specified test categories and generates Allure results."
    echo "  --unit:        Run unit tests."
    echo "  --integration: Run integration tests."
    echo "  --e2e:         Run end-to-end tests."
    echo "  --all:         Run all test categories."
    echo "  --help, -h:    Show this help message."
    exit 0
fi

# --- Construct pytest command ---
MARKER_ARGS=""
TEST_CATEGORIES_TO_RUN=""

if [ "$RUN_UNIT" = true ] ; then
    MARKER_ARGS+="unit "
    TEST_CATEGORIES_TO_RUN+="Unit "
fi
if [ "$RUN_INTEGRATION" = true ] ; then
    MARKER_ARGS+="integration "
    TEST_CATEGORIES_TO_RUN+="Integration "
fi
if [ "$RUN_E2E" = true ] ; then
    MARKER_ARGS+="e2e "
    TEST_CATEGORIES_TO_RUN+="E2E "
fi

# Trim trailing space
MARKER_ARGS=$(echo "${MARKER_ARGS}" | sed 's/ *$//g')
TEST_CATEGORIES_TO_RUN=$(echo "${TEST_CATEGORIES_TO_RUN}" | sed 's/ *$//g')

if [ -z "$MARKER_ARGS" ]; then
    echo "Error: No test categories selected to run. Use --unit, --integration, --e2e, or --all."
    exit 1
fi

# Combine markers with 'or' for pytest -m expression
PYTEST_MARKER_EXPR=$(echo "${MARKER_ARGS}" | sed 's/ / or /g')

# --- Clean previous results ---
echo "Cleaning old Allure results..."
rm -rf "${ALLURE_RESULTS_DIR}"
mkdir -p "${ALLURE_RESULTS_DIR}"

# --- Run Tests ---
echo "Running Pytest for categories: [${TEST_CATEGORIES_TO_RUN}]..."
echo "Executing: ${PYTEST_CMD} -v -m "${PYTEST_MARKER_EXPR}" --alluredir=${ALLURE_RESULTS_DIR}"

${PYTEST_CMD} -v -m "${PYTEST_MARKER_EXPR}" --alluredir="${ALLURE_RESULTS_DIR}"
EXIT_CODE=$?

# --- Report Status ---
if [ $EXIT_CODE -eq 0 ]; then
  echo "Tests completed successfully."
else
  echo "Tests failed with exit code $EXIT_CODE."
fi

echo "Allure results generated in: ${ALLURE_RESULTS_DIR}"

# --- Generate and Open Report --- 
echo "Generating Allure report..."
allure generate "${ALLURE_RESULTS_DIR}" --clean -o allure-report

if [ $? -eq 0 ]; then
  echo "Opening Allure report in browser..."
  allure open allure-report
else
    echo "Allure report generation failed."
fi

# --- Return Exit Code ---
exit $EXIT_CODE 