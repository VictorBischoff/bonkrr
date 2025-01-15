"""UI themes and styling for the bunkrr package."""
from rich.theme import Theme

# Default theme for consistent styling
DEFAULT_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red",
    "success": "green",
    "progress.percentage": "cyan",
    "progress.download": "green",
    "progress.data.speed": "cyan",
    "url": "blue underline",
    "filename": "bright_cyan",
    "stats": "magenta"
}) 
