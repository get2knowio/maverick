#!/bin/bash
# notify.sh
# Sends notifications to ntfy.sh when NTFY_TOPIC is set
# Usage: notify.sh <event_type> [message]
#
# Environment variables:
#   NTFY_TOPIC    - The ntfy.sh topic to publish to (required for notifications)
#   NTFY_SERVER   - Optional custom ntfy server (default: ntfy.sh)
#
# Event types:
#   permission    - A permission was allowed
#   spec_start    - Started working on a spec
#   review        - Started code review phase
#   testing       - Entered testing phase
#   complete      - Spec completed (all tasks done)
#   error         - An error occurred

set -e

EVENT_TYPE="${1:-unknown}"
MESSAGE="${2:-}"

# Exit silently if NTFY_TOPIC is not set
if [ -z "$NTFY_TOPIC" ]; then
    exit 0
fi

NTFY_SERVER="${NTFY_SERVER:-ntfy.sh}"

# Set title and priority based on event type
case "$EVENT_TYPE" in
    permission)
        TITLE="Permission Allowed"
        PRIORITY="low"
        TAGS="white_check_mark"
        MESSAGE="${MESSAGE:-A permission was granted}"
        ;;
    spec_start)
        TITLE="Spec Started"
        PRIORITY="default"
        TAGS="rocket"
        MESSAGE="${MESSAGE:-Started working on specification}"
        ;;
    review)
        TITLE="Code Review"
        PRIORITY="default"
        TAGS="mag"
        MESSAGE="${MESSAGE:-Starting code review phase}"
        ;;
    testing)
        TITLE="Testing Phase"
        PRIORITY="default"
        TAGS="test_tube"
        MESSAGE="${MESSAGE:-Entered testing phase}"
        ;;
    complete)
        TITLE="Spec Complete"
        PRIORITY="high"
        TAGS="tada"
        MESSAGE="${MESSAGE:-All tasks completed successfully}"
        ;;
    error)
        TITLE="Error Occurred"
        PRIORITY="urgent"
        TAGS="warning,rotating_light"
        MESSAGE="${MESSAGE:-An error was encountered}"
        ;;
    *)
        TITLE="Maverick Event"
        PRIORITY="default"
        TAGS="bell"
        MESSAGE="${MESSAGE:-Event: $EVENT_TYPE}"
        ;;
esac

# Send notification via curl
curl -s \
    -H "Title: $TITLE" \
    -H "Priority: $PRIORITY" \
    -H "Tags: $TAGS" \
    -d "$MESSAGE" \
    "https://$NTFY_SERVER/$NTFY_TOPIC" > /dev/null 2>&1 || true

# Always exit successfully so we don't block the workflow
exit 0
