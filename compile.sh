#!/bin/bash

# This script finds all .ui files in the SOURCE_DIR and compiles them
# into .py files in the DEST_DIR, prefixing them with "ui_".
# It also compiles the .qrc resource file into a .py file.

# --- Configuration ---
SOURCE_DIR="src/theme/design"           # The directory containing your .ui files.
DEST_DIR="src/ui"             # The directory where the .py files will be saved.
RESOURCE_FILE="src/resources.qrc"  # Path to the .qrc file

# --- Script ---

# Ensure the destination directory exists
mkdir -p "$DEST_DIR"

echo "Source directory:      $SOURCE_DIR"
echo "Destination directory: $DEST_DIR"
echo "-------------------------------------"

# Compile all .ui files
for UI_FILE in "$SOURCE_DIR"/*.ui; do
  if [ -f "$UI_FILE" ]; then
    BASENAME=$(basename "$UI_FILE" .ui)
    PY_FILE="$DEST_DIR/ui_$BASENAME.py"
    echo "Compiling $UI_FILE  ->  $PY_FILE"
    pyside6-uic "$UI_FILE" -o "$PY_FILE"
  fi
done

# Compile the resource file
if [ -f "$RESOURCE_FILE" ]; then
  RESOURCE_PY="src/resources_rc.py"
  echo "Compiling resource file $RESOURCE_FILE -> $RESOURCE_PY"
  pyside6-rcc "$RESOURCE_FILE" -o "$RESOURCE_PY"
else
  echo "Warning: Resource file not found: $RESOURCE_FILE"
fi

echo "-------------------------------------"
echo "UI and resource compilation finished."
