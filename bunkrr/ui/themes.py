"""UI themes and styling for the bunkrr package."""
from rich.theme import Theme

# Default theme for consistent styling
DEFAULT_THEME = Theme({
    # Status colors
    "info": "bright_cyan",
    "warning": "bright_yellow",
    "error": "bright_red",
    "success": "bright_green",
    
    # Progress colors
    "progress.percentage": "bright_cyan",
    "progress.download": "bright_green",
    "progress.data.speed": "bright_cyan",
    "progress.description": "bright_white",
    "progress.remaining": "bright_magenta",
    "progress.spinner": "bright_cyan",
    
    # Content colors
    "url": "blue underline",
    "filename": "bright_cyan",
    "stats": "bright_magenta",
    "stats.value": "bright_white",
    
    # Panel styles
    "panel.border": "bright_cyan",
    "panel.title": "bright_white",
    
    # Table styles
    "table.header": "bright_white bold",
    "table.row": "bright_cyan",
    
    # Summary styles
    "summary.success": "bright_green",
    "summary.error": "bright_red",
    "summary.info": "bright_cyan",
    "summary.title": "bright_white bold"
}) 
