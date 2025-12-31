#!/bin/bash
# get-changed-files.sh
# Returns JSON list of files changed compared to origin/main
# Usage: get-changed-files.sh [base_ref]
# Returns: [{"file": "...", "status": "A|M|D|R"}]

BASE=${1:-origin/main}

# Get the diff with name and status
CHANGES=$(git diff "$BASE"...HEAD --name-status 2>/dev/null)

if [ -z "$CHANGES" ]; then
    echo "[]"
    exit 0
fi

# Build JSON array
echo "["
FIRST=true
while IFS=$'\t' read -r STATUS FILE RENAMED_TO; do
    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        echo ","
    fi

    # Handle renames (R status has two files)
    if [[ "$STATUS" == R* ]]; then
        # Extract rename percentage if present (e.g., R100)
        echo -n "  {\"status\": \"R\", \"file\": \"$RENAMED_TO\", \"renamed_from\": \"$FILE\"}"
    else
        echo -n "  {\"status\": \"$STATUS\", \"file\": \"$FILE\"}"
    fi
done <<< "$CHANGES"
echo ""
echo "]"
