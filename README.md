# 💻 PyQt Application

A project scaffold for developing desktop applications using **PyQt**, supporting GUI design via **Qt Designer** and easy integration with backend features such as config, database, and more.

## 🧾 Project Structure

```
├── .gitignore
├── README.md
├── requirement.txt
├── src/
│   ├── App.spec
│   ├── config.ini
│   ├── main.py
│   ├── services/
│   │   ├── config.py
│   │   ├── db.py
│   │   └── version.py
│   ├── theme/
│   │   ├── design/
│   │   │   └── ui_login.ui
│   │   ├── icon/
│   │   │   └── favicon.ico
│   │   └── login.qss
│   ├── ui/
│   │   └── forms/
│   │       └── ui_login.py
│   └── views/
│       └── login.py
└── tools/
    ├── build.py
    └── gen_ui.py
```

## 🚀 Installation & Development Guide

### 1. Set Up Virtual Environment

- Create and activate a virtual environment:

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

- Install required packages from `requirement.txt`:

```bash
pip install -r requirement.txt
```

---

### 2. Design UI with Qt Designer

- Download Qt Designer at: [https://build-system.fman.io/qt-designer-download](https://build-system.fman.io/qt-designer-download)
- Design and save `.ui` files into the `src/theme/design/` folder.

---

### 3. Customize UI with QSS

You can customize the interface using `.qss` files located in:

```bash
src/theme/<folder-name>/your-style.qss
```

---

### 4. Generate `.py` Files from `.ui`

Run the following command to convert `.ui` to `.py`:

```bash
python .\tools\gen_ui.py
```
#### window:
```
python tools\genui.py

```
The output `.py` files will be placed in:

```bash
src/ui/forms/
```

---

### 5. Handle Events & Logic

Implement business logic and event handling in:

```bash
src/views/
```

For example: `login.py` for handling login functionality.

---

### 6. Entry Point

The main entry point for running the app in development:

```bash
python src/main.py
```

You can customize `main.py` to integrate views, configurations, and initialize the UI.

---

## 📦 Build the Application (Optional)

You can build the project into an `.exe` file by running:

```bash
python ./tools/build.py
```

---

## 📦 Build the Setup.exe with Inno Setup (Optional)

After you have built the application with the command above, you can package the application into a `Setup.exe` installer for distribution.

### Requirements

* [Inno Setup](https://jrsoftware.org/isinfo.php) must be installed on your system.

### Steps

1. Install **Inno Setup** (if not already installed).
2. Open **Inno Setup Compiler**.
3. Load the script:

   * Go to **File → Open...** and select `build_setup.iss` from the project root.
4. Build the installer:

   * Press **F9** or click **Build → Compile**.
5. After the build completes, the generated `Setup.exe` will be available in the `Output` folder (default under your project directory).

---

## 📌 Notes

- The project follows a clear separation between UI (frontend), logic handling (views), and backend services.
- Easy to extend, maintain, and scale.

---

## 🧑‍💻 Author

TuyenDV – R&D AI Team Leader
NguyenNC – R&D Fullstack Developer

---

## 📄 License

> CO-WELL Asia License
