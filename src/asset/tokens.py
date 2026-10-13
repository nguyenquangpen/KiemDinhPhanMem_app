"""Design tokens shared by the QSS files and by widgets that paint or style themselves.

Keep these values in sync with the hex codes used in ``src/asset/*.qss``.
"""

# --- Surfaces ---
BG = "#F5F6F6"  # window / page background
SURFACE = "#FFFFFF"  # cards, sidebar, header
ROW_ALT = "#FAFAFA"  # zebra rows, subtle panels
BORDER = "#E3E5E5"  # card borders, dividers
BORDER_STRONG = "#D3D7D6"  # input borders, dotted dividers
ROW_LINE = "#ECEEEE"  # line between table rows

# --- Text ---
TEXT = "#1E2B29"
TEXT_MUTED = "#5B6866"
TEXT_SUBTLE = "#8A9593"  # icons / placeholder only, not body text

# --- Primary (green): main action, OK ---
PRIMARY = "#2F8A55"
PRIMARY_HOVER = "#277449"
PRIMARY_TEXT = "#226B41"
PRIMARY_SOFT = "#EAF5EE"
PRIMARY_SOFT_BORDER = "#BFDFCB"

# --- Secondary (blue): outline actions, focus ---
SECONDARY = "#2E6DB4"
SECONDARY_TEXT = "#1F4F86"
SECONDARY_SOFT = "#F1F7FD"

# --- Danger (red): NG, delete ---
DANGER = "#C2453B"
DANGER_TEXT = "#9E2F27"
DANGER_ICON = "#B23A31"
DANGER_SOFT = "#FCEDEC"
DANGER_BORDER = "#E3C4C1"

# --- Warning (amber): running, unsaved ---
WARNING = "#B26B00"
WARNING_TEXT = "#8A5300"
WARNING_SOFT = "#FFF6E5"

# --- Neutral ---
NEUTRAL_SOFT = "#EEF0F0"
NEUTRAL_TEXT = "#4A5654"

# --- Fonts ---
FONT_UI = "Poppins"
FONT_BODY = "Noto Serif"
FONT_MONO = "Consolas"
