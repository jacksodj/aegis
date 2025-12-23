#!/bin/bash
# Test script for Researcher Agent
# Usage: ./test.sh [test_name]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="${BASE_URL:-http://localhost:8080}"
VERBOSE="${VERBOSE:-false}"

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Test functions
test_health() {
    log_info "Testing /ping endpoint..."
    response=$(curl -s -w "\n%{http_code}" "$BASE_URL/ping")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" = "200" ]; then
        log_info "Health check passed: $body"
        return 0
    else
        log_error "Health check failed with status $http_code"
        return 1
    fi
}

test_agent_card() {
    log_info "Testing /.well-known/agent-card.json endpoint..."
    response=$(curl -s -w "\n%{http_code}" "$BASE_URL/.well-known/agent-card.json")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" = "200" ]; then
        log_info "Agent card retrieved successfully"
        if [ "$VERBOSE" = "true" ]; then
            echo "$body" | jq '.'
        else
            echo "$body" | jq '{name, version, description}'
        fi
        return 0
    else
        log_error "Agent card failed with status $http_code"
        return 1
    fi
}

test_sync_invocation() {
    log_info "Testing synchronous invocation..."

    payload=$(cat <<EOF
{
  "jsonrpc": "2.0",
  "id": "test-sync-$(date +%s)",
  "method": "tasks/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{
        "kind": "text",
        "text": "{\"topic\": \"artificial intelligence in healthcare\", \"workflow_id\": \"test-wf-sync\", \"parameters\": {\"depth\": \"basic\", \"max_results\": 5}}"
      }]
    }
  }
}
EOF
)

    response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/invocations" \
        -H "Content-Type: application/json" \
        -d "$payload")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" = "200" ]; then
        log_info "Sync invocation successful"
        if [ "$VERBOSE" = "true" ]; then
            echo "$body" | jq '.'
        else
            echo "$body" | jq '{id, result: {topic: .result.topic, research_type: .result.research_type, executive_summary: .result.executive_summary}}'
        fi
        return 0
    else
        log_error "Sync invocation failed with status $http_code"
        echo "$body"
        return 1
    fi
}

test_async_invocation() {
    log_info "Testing asynchronous invocation..."

    # Use webhook.site or similar for callback testing
    callback_url="${CALLBACK_URL:-http://webhook.site/test-callback}"
    log_warning "Using callback URL: $callback_url"
    log_warning "Note: You need a real callback endpoint to verify async execution"

    payload=$(cat <<EOF
{
  "jsonrpc": "2.0",
  "id": "test-async-$(date +%s)",
  "method": "tasks/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{
        "kind": "text",
        "text": "{\"topic\": \"quantum computing applications\", \"workflow_id\": \"test-wf-async\", \"parameters\": {\"depth\": \"comprehensive\"}, \"callback_url\": \"$callback_url\", \"callback_token\": \"test-token-123\"}"
      }]
    }
  }
}
EOF
)

    response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/invocations" \
        -H "Content-Type: application/json" \
        -d "$payload")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" = "200" ]; then
        log_info "Async invocation accepted"
        echo "$body" | jq '.'
        log_info "Check your callback endpoint for results"
        return 0
    else
        log_error "Async invocation failed with status $http_code"
        echo "$body"
        return 1
    fi
}

test_detailed_health() {
    log_info "Testing /health endpoint..."
    response=$(curl -s -w "\n%{http_code}" "$BASE_URL/health")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" = "200" ]; then
        log_info "Detailed health check passed"
        echo "$body" | jq '.'
        return 0
    else
        log_error "Detailed health check failed with status $http_code"
        return 1
    fi
}

run_all_tests() {
    log_info "Running all tests against $BASE_URL"
    echo ""

    local failed=0

    test_health || ((failed++))
    echo ""

    test_agent_card || ((failed++))
    echo ""

    test_detailed_health || ((failed++))
    echo ""

    test_sync_invocation || ((failed++))
    echo ""

    test_async_invocation || ((failed++))
    echo ""

    if [ $failed -eq 0 ]; then
        log_info "All tests passed! ✓"
        return 0
    else
        log_error "$failed test(s) failed ✗"
        return 1
    fi
}

# Main execution
main() {
    local test_name="${1:-all}"

    # Check if server is reachable
    if ! curl -s -f -o /dev/null --max-time 5 "$BASE_URL/ping"; then
        log_error "Cannot reach agent at $BASE_URL"
        log_error "Make sure the agent is running:"
        log_error "  docker-compose up -d"
        log_error "or:"
        log_error "  python -m src.main"
        exit 1
    fi

    case "$test_name" in
        health)
            test_health
            ;;
        agent-card)
            test_agent_card
            ;;
        sync)
            test_sync_invocation
            ;;
        async)
            test_async_invocation
            ;;
        detailed-health)
            test_detailed_health
            ;;
        all)
            run_all_tests
            ;;
        *)
            log_error "Unknown test: $test_name"
            echo ""
            echo "Usage: $0 [test_name]"
            echo ""
            echo "Available tests:"
            echo "  health           - Test /ping endpoint"
            echo "  agent-card       - Test agent metadata endpoint"
            echo "  detailed-health  - Test /health endpoint"
            echo "  sync             - Test synchronous invocation"
            echo "  async            - Test asynchronous invocation with callback"
            echo "  all              - Run all tests (default)"
            echo ""
            echo "Environment variables:"
            echo "  BASE_URL         - Agent URL (default: http://localhost:8080)"
            echo "  CALLBACK_URL     - Callback URL for async tests"
            echo "  VERBOSE          - Show full responses (default: false)"
            exit 1
            ;;
    esac
}

# Run main with arguments
main "$@"
