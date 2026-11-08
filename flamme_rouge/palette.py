"""Couleurs de l'application (sans tkinter, pour que le dessin du plateau reste testable)."""

# Interface (thème sombre)
BG = "#0b1220"  # fond de fenêtre
PANEL = "#111a2e"  # bandeaux
CARD = "#17233f"  # cartes
CARD_HI = "#1f3057"  # carte survolée
BORDER = "#2a3a60"
DISABLED = "#18233b"  # bouton désactivé
TEXT = "#e8edf7"
MUTED = "#93a4c3"
FAINT = "#5d6f94"
ACCENT = "#ff4d4f"  # la flamme rouge
ACCENT_HI = "#ff7074"
ACCENT_DK = "#d93638"
GOOD = "#34d399"

# Équipes : 1 rouge, 2 bleu, 3 vert, 4 jaune ; 5 rose et 6 blanc (extension Peloton)
TEAM_FILL = ["#ff4d4f", "#3b82f6", "#22c55e", "#facc15", "#f472b6", "#f1f5f9"]
TEAM_TEXT = ["#ff7b7d", "#6aa7ff", "#4ade80", "#fde047", "#f9a8d4", "#f8fafc"]  # pour du texte sur fond sombre
LABEL_ON_FILL = ["white", "white", "black", "black", "black", "black"]

# Plateau
GRASS = "#1f5a3b"
GRASS_DARK = "#194a31"
TERRAIN_FILL = {".": "#4b5766", "A": "#c8741e", "D": "#2f80c0"}
TERRAIN_SYMBOL_COLOR = {".": "#8fa0b5", "A": "#fff0dd", "D": "#e1f2ff"}
BEYOND_FILL = "#6b7a90"  # cases après la ligne d'arrivée
ROAD_EDGE = "#e2e8f0"  # lignes blanches au bord de la route
ROAD_OUTLINE = "#364152"
LANE_LINE = "#64748b"
SQUARE_NUMBER = "#b7c6dc"
SHADOW = "#143626"
CURRENT_RING = "#fde047"
RIDER_OUTLINE = "#ffffff"

# Météo (extension) : couleurs des panneaux
WEATHER_FILL = {"travers": "#22c55e", "arriere": "#facc15", "face": "#38bdf8", "pluie": "#1e293b"}
WEATHER_TEXT = {"travers": "#052e16", "arriere": "#422006", "face": "#082f49", "pluie": "#e2e8f0"}
CRASH_MARK = "#ff4d4f"

# Profil d'étape
PROFILE_FILL = {".": "#64748b", "A": "#f59e0b", "D": "#38bdf8"}
PROFILE_LINE = "#e8edf7"
