#!/bin/bash
# Remove the first line of every file in a directory
# Usage:
#   ./remove_first_line_all.sh /path/to/dir           # all files
#   ./remove_first_line_all.sh /path/to/dir "*.txt"   # only matching pattern

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "Usage: $0 <directory> [pattern]"
    echo "Example: $0 /tmp \"*.txt\""
    exit 1
fi

DIR="$1"
PATTERN="${2:-*}"

if [ ! -d "$DIR" ]; then
    echo "Error: '$DIR' is not a directory."
    exit 1
fi

cd "$DIR" || exit 1

for FILENAME in $PATTERN; do
    # Skip if glob did not match anything
    [ "$FILENAME" = "$PATTERN" ] && [ ! -e "$FILENAME" ] && continue

    if [ ! -f "$FILENAME" ]; then
        # Skip non-regular files
        continue
    fi

    echo "Processing '$FILENAME'..."

    TEMP_FILE=$(mktemp)    # mktemp is standard and safe on Linux [web:7]

    # Skip the first line and write the rest to the temporary file
    tail -n +2 "$FILENAME" > "$TEMP_FILE"  # Loop pattern similar to common *.txt loops [web:6]

    # Replace original file with the modified content
    mv "$TEMP_FILE" "$FILENAME"
done

echo "Done."
