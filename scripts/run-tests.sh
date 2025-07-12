#!/bin/bash

# Test runner script with different options

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_usage() {
    echo "Usage: $0 [option]"
    echo "Options:"
    echo "  all      - Run all tests (default)"
    echo "  unit     - Run unit tests only"
    echo "  integration - Run integration tests only"
    echo "  coverage - Run with coverage report"
    echo "  watch    - Run in watch mode"
    echo "  specific <test_file> - Run specific test file"
}

run_tests() {
    local test_type=$1
    
    echo -e "${GREEN}Running $test_type tests...${NC}\n"
    
    case $test_type in
        all)
            pytest tests/
            ;;
        unit)
            pytest tests/unit/ -m "not integration"
            ;;
        integration)
            pytest tests/integration/ -m "integration"
            ;;
        coverage)
            pytest tests/ --cov=api --cov-report=html --cov-report=term
            echo -e "\n${GREEN}Coverage report generated in htmlcov/index.html${NC}"
            ;;
        watch)
            pytest-watch tests/ -- -v
            ;;
        specific)
            if [ -z "$2" ]; then
                echo -e "${RED}Error: Please specify a test file${NC}"
                exit 1
            fi
            pytest "$2" -v
            ;;
        *)
            print_usage
            exit 1
            ;;
    esac
}

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest is not installed${NC}"
    echo "Run: pip install -r requirements.txt"
    exit 1
fi

# Main execution
if [ $# -eq 0 ]; then
    run_tests "all"
else
    run_tests "$@"
fi