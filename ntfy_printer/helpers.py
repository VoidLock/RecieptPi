"""Helper functions for priority detection and emoji handling."""

import re
from . import config


def strip_emojis(text):
    """Remove or replace emojis with ASCII alternatives for thermal printer.
    
    Replaces specific emoji with text alternatives first, then removes
    any remaining emoji characters.
    
    Args:
        text (str): Text potentially containing emoji
        
    Returns:
        str: Text with emoji removed or replaced
    """
    # First try specific mappings
    for emoji, replacement in config.EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    
    # Remove any remaining emojis (Unicode ranges for common emoji blocks)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # extended symbols
        "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)
    return text


def detect_priority(message, payload=None):
    """Detect priority level from ntfy message payload.
    
    Supports:
    - ntfy numeric priority (1-5 scale, where 5=max, 1=min)
    - Explicit priority field in JSON payload
    - Priority header values (min, low, default, high, max, urgent)
    
    Args:
        message (str): Raw message text (unused, kept for compatibility)
        payload (dict): ntfy message payload with priority data
        
    Returns:
        str: One of ("max", "high", "default", "low", "min")
    """
    if not payload or not isinstance(payload, dict):
        return "default"
    
    # Check for numeric priority (ntfy uses 1-5 scale: 5=max, 4=high, 3=default, 2=low, 1=min)
    priority_value = payload.get("priority")
    if priority_value is not None:
        try:
            p = int(priority_value)
            if p >= 5:
                return "max"
            elif p >= 4:
                return "high"
            elif p >= 3:
                return "default"
            elif p >= 2:
                return "low"
            else:
                return "min"
        except (ValueError, TypeError):
            pass
    
    # Check for string priority values (e.g., from headers or explicit field)
    priority_str = payload.get("priority_str", payload.get("priority_level", "")).lower()
    if priority_str:
        if priority_str in ["5", "urgent", "critical", "max", "emergency"]:
            return "max"
        elif priority_str in ["4", "high"]:
            return "high"
        elif priority_str in ["3", "normal", "default", "medium"]:
            return "default"
        elif priority_str in ["2", "low"]:
            return "low"
        elif priority_str in ["1", "min", "minimal"]:
            return "min"
    
    return "default"


def get_priority_symbol(priority_level):
    """Get the alert symbol(s) and count for priority level.
    
    Args:
        priority_level (str): One of ("max", "high", "default", "low", "min")
        
    Returns:
        tuple: (symbol, count) - symbol is emoji str, count is number of repetitions
    """
    symbols = {
        "max": ("⚡", 3),      # 3 lightning bolts for max
        "high": ("⚡", 2),     # 2 lightning bolts for high
        "default": ("⚡", 1),  # 1 lightning bolt for default
        "low": ("↓", 1),       # Down arrow for low
        "min": ("•", 1),       # Bullet for minimal
    }
    return symbols.get(priority_level, ("⚡", 1))


def draw_priority_banner(draw, x, y, width, height, priority, font, text_color=(0, 0, 0), bg_color=(200, 200, 200)):
    """Draw a priority banner with visual styling based on priority level.
    
    Creates a filled rectangle with hatching pattern that varies by priority.
    
    Args:
        draw: PIL ImageDraw object
        x, y (int): Top-left coordinates
        width, height (int): Banner dimensions in pixels
        priority (str): One of ("critical", "high", "medium", "low")
        font: PIL Font for text rendering
        text_color (tuple): RGB tuple for text (default black)
        bg_color (tuple): RGB tuple for background (default gray)
    
    Returns:
        str: The text that was drawn in the banner
    """
    # Define visual styles per priority
    styles = {
        "critical": {
            "text": "⚠ CRITICAL ⚠",
            "fill": (255, 100, 100),  # Red
            "pattern": "heavy",  # Dense shading
        },
        "high": {
            "text": "● HIGH ●",
            "fill": (255, 180, 100),  # Orange
            "pattern": "medium",
        },
        "medium": {
            "text": "○ MEDIUM ○",
            "fill": (255, 255, 100),  # Yellow
            "pattern": "light",
        },
        "low": {
            "text": "- LOW -",
            "fill": (200, 255, 200),  # Light green
            "pattern": "minimal",
        },
    }
    
    style = styles.get(priority.lower(), styles["medium"])
    fill = style["fill"]
    banner_text = style["text"]
    pattern = style["pattern"]
    
    # Draw background rectangle with border
    border_width = 2
    draw.rectangle([x, y, x + width - 1, y + height - 1], fill=fill, outline=(0, 0, 0), width=border_width)
    
    # Add pattern/shading based on priority (thicker line = higher priority)
    if pattern == "heavy":
        # Dense lines for critical
        for line_y in range(y + 5, y + height - 5, 2):
            draw.line([x + 5, line_y, x + width - 5, line_y], fill=(100, 0, 0), width=1)
    elif pattern == "medium":
        # Medium spacing for high
        for line_y in range(y + 5, y + height - 5, 3):
            draw.line([x + 5, line_y, x + width - 5, line_y], fill=(150, 80, 0), width=1)
    elif pattern == "light":
        # Light spacing for medium
        for line_y in range(y + 5, y + height - 5, 5):
            draw.line([x + 5, line_y, x + width - 5, line_y], fill=(150, 150, 0), width=1)
    
    # Draw text centered in banner
    text_bbox = draw.textbbox((0, 0), banner_text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    text_x = x + (width - text_width) // 2
    text_y = y + (height - text_height) // 2
    draw.text((text_x, text_y), banner_text, font=font, fill=(0, 0, 0))
    
    return banner_text
