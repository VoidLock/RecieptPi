# Priority-Based Lightning Bolt Feature

## Quick Summary

The alert symbol at the top of printed messages now reflects message priority automatically:

| Symbol | Quantity | Triggered By | Use Case |
|--------|----------|--------------|----------|
| ⚡ | **3 bolts** (MAX) | critical, emergency, urgent, alert, alarm | System failures, emergencies |
| ⚡ | **2 bolts** (HIGH) | important, action required, attention | Important tasks |
| ⚡ | **1 bolt** (DEFAULT) | no keywords | Regular notifications |
| ↓ | **1 arrow** (LOW) | low priority, fyi, low importance | Low priority items |
| • | **1 bullet** (MIN) | minimal, optional, nice to have | Optional info |

## How It Works

The system scans each message for priority keywords and automatically displays the appropriate number of lightning bolts (or alternative symbols for low/minimal priorities).

### Plain Text Example
```bash
# These commands automatically show the correct number of bolts:

curl -d "CRITICAL SYSTEM DOWN" https://ntfy.sh/my-topic      # Shows: ⚡⚡⚡
curl -d "URGENT ACTION NEEDED" https://ntfy.sh/my-topic      # Shows: ⚡⚡⚡
curl -d "Regular message" https://ntfy.sh/my-topic           # Shows: ⚡
curl -d "Low priority update" https://ntfy.sh/my-topic       # Shows: ↓
curl -d "Minimal optional info" https://ntfy.sh/my-topic     # Shows: •
```

### JSON Payload Example
You can also explicitly set priority in JSON:

```bash
curl -X POST https://ntfy.sh/my-topic \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Database offline",
    "priority": "critical"
  }'
```

Supported JSON priority values: `critical`, `max`, `emergency`, `high`, `urgent`, `medium`, `default`, `normal`, `low`, `min`, `minimal`, `info`

## Testing from Desktop

Copy and paste these commands directly into your terminal:

### Test All Levels
```bash
TOPIC="YOUR_TOPIC_HERE"

echo "MAX (⚡⚡⚡):"
curl -d "CRITICAL SYSTEM FAILURE" https://ntfy.sh/$TOPIC

echo -e "\n\nHIGH (⚡⚡):"
curl -d "URGENT ACTION REQUIRED" https://ntfy.sh/$TOPIC

echo -e "\n\nDEFAULT (⚡):"
curl -d "Regular notification" https://ntfy.sh/$TOPIC

echo -e "\n\nLOW (↓):"
curl -d "Low priority item" https://ntfy.sh/$TOPIC

echo -e "\n\nMIN (•):"
curl -d "Minimal optional task" https://ntfy.sh/$TOPIC
```

### Test with Subtext
```bash
curl -X POST https://ntfy.sh/YOUR_TOPIC \
  -H "Content-Type: application/json" \
  -d '{
    "type": "text_with_subtext",
    "message": "CRITICAL ALERT",
    "subtext": "Database server is down - Contact DBA"
  }'
```

### Test JSON with Priority
```bash
curl -X POST https://ntfy.sh/YOUR_TOPIC \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Building Fire Alarm",
    "priority": "critical",
    "subtext": "Evacuate immediately"
  }'
```

## Keyword Lists

### Triggers MAX (⚡⚡⚡)
- critical
- emergency
- urgent
- alert
- alarm

### Triggers HIGH (⚡⚡)
- important
- action required
- attention

### Triggers LOW (↓)
- low priority
- fyi
- low importance

### Triggers MIN (•)
- minimal
- optional
- nice to have

## Features

✓ **Automatic Detection**: No configuration needed - just send messages
✓ **Backward Compatible**: Existing code works unchanged
✓ **Works Everywhere**: Plain text, JSON, with/without subtext
✓ **Visual Priority**: At a glance, see importance from bolt count
✓ **Customizable**: Modify keywords in `detect_priority()` function if needed

## Implementation Details

The feature is implemented through:

1. **`detect_priority(message, payload=None)`** - Analyzes message for keywords and returns priority level
2. **`get_priority_symbol(priority_level)`** - Returns appropriate symbol and count for the priority
3. **Updated `create_layout()`** - Automatically detects priority and renders correct symbols
4. **Updated `print_msg()`** - Passes detected priority to layout rendering

All three new functions are in `app.py` and fully integrated with existing message rendering pipeline.
