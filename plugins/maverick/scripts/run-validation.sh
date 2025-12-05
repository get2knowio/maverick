#!/bin/bash
# run-validation.sh
# Runs full validation suite and returns structured JSON results
# This is a generic version that can be customized per project
# Returns: {"all_passed": bool, "checks": [...]}

# Temp files for capturing output
OUTPUTS_DIR=$(mktemp -d)

cleanup() {
    rm -rf "$OUTPUTS_DIR"
}
trap cleanup EXIT

# Array to store check results
CHECKS=()

# Function to run a check and record results
run_check() {
    local name="$1"
    local cmd="$2"
    local output_file="$OUTPUTS_DIR/$name.out"

    eval "$cmd" 2>"$output_file"
    local status=$?

    # Escape output for JSON
    local output
    output=$(cat "$output_file" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo '""')

    local passed="false"
    if [ $status -eq 0 ]; then
        passed="true"
    fi

    CHECKS+=("{\"name\": \"$name\", \"passed\": $passed, \"exit_code\": $status, \"output\": $output}")
}

# Detect project type and run appropriate checks
if [ -f "Cargo.toml" ]; then
    # Rust project
    run_check "fmt" "cargo fmt --all -- --check"
    run_check "clippy" "cargo clippy --all-targets --all-features -- -D warnings"
    run_check "build" "cargo build --all-targets"
    run_check "test" "cargo test --all-features"
elif [ -f "package.json" ]; then
    # Node.js project
    if [ -f "package-lock.json" ]; then
        run_check "install" "npm ci"
    fi
    if grep -q '"lint"' package.json 2>/dev/null; then
        run_check "lint" "npm run lint"
    fi
    if grep -q '"build"' package.json 2>/dev/null; then
        run_check "build" "npm run build"
    fi
    if grep -q '"test"' package.json 2>/dev/null; then
        run_check "test" "npm test"
    fi
elif [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
    # Python project
    if command -v ruff &> /dev/null; then
        run_check "lint" "ruff check ."
    elif command -v flake8 &> /dev/null; then
        run_check "lint" "flake8 ."
    fi
    if command -v pytest &> /dev/null; then
        run_check "test" "pytest"
    fi
elif [ -f "go.mod" ]; then
    # Go project
    run_check "fmt" "gofmt -l ."
    run_check "vet" "go vet ./..."
    run_check "build" "go build ./..."
    run_check "test" "go test ./..."
else
    # Generic - just check if there's a Makefile
    if [ -f "Makefile" ]; then
        if grep -q "^lint:" Makefile 2>/dev/null; then
            run_check "lint" "make lint"
        fi
        if grep -q "^test:" Makefile 2>/dev/null; then
            run_check "test" "make test"
        fi
        if grep -q "^build:" Makefile 2>/dev/null; then
            run_check "build" "make build"
        fi
    fi
fi

# Build final JSON
ALL_PASSED="true"
CHECKS_JSON=""
for i in "${!CHECKS[@]}"; do
    if [ $i -gt 0 ]; then
        CHECKS_JSON="$CHECKS_JSON, "
    fi
    CHECKS_JSON="$CHECKS_JSON${CHECKS[$i]}"

    # Check if this check failed
    if [[ "${CHECKS[$i]}" == *'"passed": false'* ]]; then
        ALL_PASSED="false"
    fi
done

cat <<EOF
{
  "all_passed": $ALL_PASSED,
  "checks": [$CHECKS_JSON]
}
EOF
