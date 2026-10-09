from pathlib import Path

class StyleManager:
    def __init__(self, style_directory: Path):
        self.style_dir = style_directory
        self.stylesheets = {}

        self.load_order = [
            "global.qss",
            "cards.qss",
            "forms.qss",
            "buttons.qss",
            "tables.qss",
            "input_card.qss",
        ]
        
        self._load_all_styles()

    def _load_all_styles(self):
        for filename in self.load_order:
            file_path = self.style_dir / filename
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read() + "\n" 
                    self.stylesheets[filename] = content
            except FileNotFoundError:
                print(f"  - not file file '{filename}' in '{file_path}'")
                self.stylesheets[filename] = ""

    def get_full_stylesheet(self) -> str:
        full_style = []
        for filename in self.load_order:
            full_style.append(self.stylesheets.get(filename, ""))
        return "".join(full_style)