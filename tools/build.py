# tools/build.py

import os
import shutil
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))

local_app_data = os.getenv('LOCALAPPDATA')
playwright_browsers_path = os.path.join(local_app_data, "ms-playwright")

def clean():
    for f in ["build", "dist"]:
        path = os.path.join(ROOT, "../", f)
        if os.path.exists(path):
            shutil.rmtree(path)

    spec = os.path.join(ROOT, "App.spec")
    if os.path.exists(spec):
        os.remove(spec)


def build():
    os.chdir(ROOT)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    cmd = [
        "pyinstaller",
        "--noconfirm",
        # "--onefile",
        "--windowed",
        "--icon=theme/icon/favicon.ico",  # This sets the executable's icon
        "--name=App",
        # "--add-data=config.ini:.",
        # "--add-data=theme/style:theme/style",
        "--add-data=theme/icon:theme/icon",
        "--add-data=asset:asset",
        "--add-data=../.env:.",
        f"--add-data={playwright_browsers_path};ms-playwright",
        "--distpath=../dist",
        "--workpath=../build",
        "main.py",
    ]

    print(f"[+] Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    print("\n[⚙️] Running post-build steps...")

    # Define paths relative to the current CWD, which is 'src'
    app_output_dir = os.path.join("..", "dist", "App")

    # The .env file is placed inside the _internal folder by PyInstaller
    source_env_path = os.path.join(app_output_dir, "_internal", ".env")

    # The desired destination is the root of the app directory, next to the .exe
    dest_env_path = os.path.join(app_output_dir, ".env")

    if os.path.exists(source_env_path):
        print(f"[+] Moving .env file from {source_env_path} to {dest_env_path}")
        shutil.move(source_env_path, dest_env_path)
        print("[✅] .env file moved successfully.")
    else:
        print(
            f"[⚠️] Warning: Could not find {source_env_path}. The .env file was not moved."
        )


if __name__ == "__main__":
    print("[⚙️] Start building App.exe (--onefile)")
    clean()
    build()
