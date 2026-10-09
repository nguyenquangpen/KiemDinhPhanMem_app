# tools/show_tree.py

import os

IGNORED_DIRS = {'.venv', '__pycache__', '.git', '.idea', 'show_tree.py'}
IGNORED_FILES_EXT = {'.pyc', '.log'}

def show_tree(folder, prefix=''):
    entries = sorted(os.listdir(folder))
    entries = [e for e in entries if e not in IGNORED_DIRS]

    for idx, name in enumerate(entries):
        path = os.path.join(folder, name)
        is_last = idx == len(entries) - 1
        connector = '└── ' if is_last else '├── '

        if os.path.isdir(path):
            print(prefix + connector + name + '/')
            extension = '    ' if is_last else '│   '
            show_tree(path, prefix + extension)
        else:
            if os.path.splitext(name)[1] in IGNORED_FILES_EXT:
                continue
            print(prefix + connector + name)

if __name__ == "__main__":
    show_tree(".")
