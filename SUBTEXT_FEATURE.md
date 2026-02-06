# Subtext Feature Documentation

## Overview
The application now supports optional subtext for plain text layouts, allowing you to print a main header with a secondary description below it.

## Usage

### Simple Text Message with Subtext
```python
from app import WhiteboardPrinter

wp = WhiteboardPrinter()
wp.print_msg("MEETING AT 3PM", subtext="Room 202")
```

### Via ntfy with JSON Payload
Create a JSON payload with `type: "text_with_subtext"`:

```json
{
  "type": "text_with_subtext",
  "message": "LUNCH DELIVERY",
  "subtext": "Building A - Main Lobby"
}
```

Post to ntfy:
```bash
curl -X POST https://ntfy.example.com/your-topic \
  -H "Content-Type: application/json" \
  -d '{"type":"text_with_subtext","message":"LUNCH DELIVERY","subtext":"Building A - Main Lobby"}'
```

## Formatting

- **Main Message**: Large bold text (70pt), supports up to 3 lines
- **Subtext**: Smaller text (24pt), gray color (80,80,80), appears below main message
- **Emoji**: All emoji in both message and subtext are automatically converted to ASCII alternatives
  - 🍕 → [pizza]
  - 🍔 → [burger]
  - ⚠️ → [warn]
  - etc.

## Examples

### Simple Alert with Location
```
Message: SECURITY ALERT
Subtext: North Gate 4
```

### Event Notification
```
Message: CONFERENCE CALL
Subtext: Zoom Room 3 - 2:30 PM
```

### Delivery Alert
```
Message: PACKAGE RECEIVED
Subtext: Dock 2 - Please Sign
```

## Technical Details

- Subtext is optional (backward compatible with existing code)
- If no subtext provided, layout renders as before
- Font automatically falls back to default bitmap if DejaVu not installed
- Image dimensions automatically adjust based on subtext presence
- All emoji filtering applies to both message and subtext

## Priority Banners (Future)

The application also includes visual priority banners that can be used for structured payloads:

```json
{
  "type": "priority_alert",
  "priority": "critical",
  "message": "SYSTEM DOWN",
  "subtext": "Database server offline"
}
```

Priority levels and visual styles:
- **critical**: ⚠ CRITICAL ⚠ (red background, dense hatching)
- **high**: ● HIGH ● (orange background, medium hatching)
- **medium**: ○ MEDIUM ○ (yellow background, light hatching)
- **low**: - LOW - (light green, minimal hatching)
