import os
import subprocess

# --- Configuration ---
SOURCE_DIR = "src/theme/design"           # The directory containing your .ui files.
DEST_DIR = "src/ui/build"             # The directory where the .py files will be saved.
RESOURCE_FILE = "src/theme/icon/resources.qrc"  # Path to the .qrc file

def compile_ui_and_resources():
    """
    Finds all .ui files in the SOURCE_DIR and compiles them
    into .py files in the DEST_DIR, prefixing them with "ui_".
    It also compiles the .qrc resource file into a .py file.
    """

    # Ensure the destination directory exists
    os.makedirs(DEST_DIR, exist_ok=True)

    # Compile all .ui files
    try:
        ui_files = [f for f in os.listdir(SOURCE_DIR) if f.endswith(".ui")]
        for ui_file in ui_files:
            source_path = os.path.join(SOURCE_DIR, ui_file)
            basename = os.path.splitext(ui_file)[0]
            py_filename = f"ui_{basename}.py"
            dest_path = os.path.join(DEST_DIR, py_filename)

            print(f"Compiling {source_path}  ->  {dest_path}")
            try:
                subprocess.run(
                    ["pyside6-uic", source_path, "-o", dest_path],
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                print(f"Error compiling {source_path}:")
                print(f"  Return Code: {e.returncode}")
                print(f"  Stderr: {e.stderr}")
                print(f"  Stdout: {e.stdout}")
            except FileNotFoundError:
                print("Error: 'pyside6-uic' command not found. Make sure PySide6 is installed and in your PATH.")
                return # Exit if the command isn't found

    except FileNotFoundError:
        print(f"Error: Source directory '{SOURCE_DIR}' not found.")
        return

    # Compile the resource file
    if os.path.isfile(RESOURCE_FILE):
        resource_py_filename = "resources_rc.py"
        resource_py_path = os.path.join("./src", resource_py_filename) # Save in current directory
        print(f"Compiling resource file {RESOURCE_FILE} -> {resource_py_path}")
        try:
            subprocess.run(
                ["pyside6-rcc", RESOURCE_FILE, "-o", resource_py_path],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error compiling {RESOURCE_FILE}:")
            print(f"  Return Code: {e.returncode}")
            print(f"  Stderr: {e.stderr}")
            print(f"  Stdout: {e.stdout}")
        except FileNotFoundError:
            print("Error: 'pyside6-rcc' command not found. Make sure PySide6 is installed and in your PATH.")
    else:
        print(f"Warning: Resource file not found: {RESOURCE_FILE}")

    print("-------------------------------------")
    print("UI and resource compilation finished.")

if __name__ == "__main__":
    compile_ui_and_resources()
