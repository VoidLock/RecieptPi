# Priority-Based Lightning Bolt Feature

## Quick Summary

The alert symbol at the top of printed messages now reflects ntfy message priority automatically using ntfy's built-in priority system:

| Symbol | Quantity | ntfy Priority | Use Case |
|--------|----------|---------------|----------|
| ⚡ | **3 bolts** (MAX) | 5 or `X-Priority: 5` | Urgent, critical |
| ⚡ | **2 bolts** (HIGH) | 4 or `X-Priority: 4` | High priority |
| ⚡ | **1 bolt** (DEFAULT) | 3 or `X-Priority: 3` | Normal priority |
| ↓ | **1 arrow** (LOW) | 2 or `X-Priority: 2` or `Priority: low` | Low priority |
| • | **1 bullet** (MIN) | 1 or `X-Priority: 1` or `Priority: min` | Minimal priority |

## How It Works

ntfy supports priority headers in HTTP requests. The app automatically reads the priority from ntfy's message payload and displays the appropriate number of lightning bolts.

### Using ntfy Priority Headers

Send messages with priority headers to ntfy:

```bash
# MAX priority (3 bolts)
curl -H "X-Priority: 5" -d "An urgent message" https://ntfy.sh/your_topic

# HIGH priority (2 bolts)
curl -H "p:4" -d "A high priority message" https://ntfy.sh/your_topic

# DEFAULT priority (1 bolt)
curl -d "Regular message" https://ntfy.sh/your_topic

# LOW priority (downward arrow)
curl -H "Priority: low" -d "Low priority message" https://ntfy.sh/your_topic

# MIN priority (bullet point)
curl -H "X-Priority: 1" -d "Minimal info only" https://ntfy.sh/your_topic
```

## Testing from Desktop

The app automatically detects priority from ntfy headers and displays the appropriate symbols. Just use ntfy's standard priority headers:

### Test All Levels
```bash
TOPIC="YOUR_TOPIC_HERE"

echo "MAX (⚡⚡⚡):"
curl -H "X-Priority: 5" -d "CRITICAL ALERT" https://ntfy.sh/$TOPIC

echo -e "\n\nHIGH (⚡⚡):"
curl -H "X-Priority: 4" -d "HIGH PRIORITY" https://ntfy.sh/$TOPIC

echo -e "\n\nDEFAULT (⚡):"
curl -d "Normal message" https://ntfy.sh/$TOPIC

echo -e "\n\nLOW (↓):"
curl -H "Priority: low" -d "Low priority item" https://ntfy.sh/$TOPIC

echo -e "\n\nMIN (•):"
curl -H "X-Priority: 1" -d "Minimal info only" https://ntfy.sh/$TOPIC
```

### Alternative Header Formats

ntfy supports multiple header formats for priority:

```bash
# These are equivalent ways to set priority 5 (urgent):
curl -H "X-Priority: 5" -d "message" https://ntfy.sh/topic
curl -H "Priority: urgent" -d "message" https://ntfy.sh/topic
curl -H "p:5" -d "message" https://ntfy.sh/topic

# Priority 4 (high):
curl -H "X-Priority: 4" -d "message" https://ntfy.sh/topic
curl -H "p:4" -d "message" https://ntfy.sh/topic

# Priority 2 (low):
curl -H "X-Priority: 2" -d "message" https://ntfy.sh/topic
curl -H "Priority: low" -d "message" https://ntfy.sh/topic

# Priority 1 (min):
curl -H "X-Priority: 1" -d "message" https://ntfy.sh/topic
curl -H "Priority: min" -d "message" https://ntfy.sh/topic
```

## Supported ntfy Headers

| Header | Values | Maps To |
|--------|--------|---------|
| `X-Priority` | 1-5 (numeric) | Priority level (1=min, 5=max) |
| `Priority` | `urgent`, `high`, `default`, `low`, `min` | Priority level |
| `p` | 1-5 (shorthand) | Priority level |

## How the App Processes Priority

1. **Receives ntfy message** with priority header (e.g., `X-Priority: 5`)
2. **ntfy stores the priority** in the message metadata
3. **App subscribes via SSE** and receives JSON payload with priority field
4. **Automatic mapping**: 5→max(⚡⚡⚡), 4→high(⚡⚡), 3→default(⚡), 2→low(↓), 1→min(•)
5. **Prints with appropriate symbol** at the top

## Features

✓ **ntfy Native**: Uses ntfy's built-in priority system
✓ **Automatic Detection**: No configuration needed - just send with headers
✓ **Standard Format**: Compatible with ntfy's 1-5 priority scale
✓ **Works Everywhere**: Plain text, JSON, with/without subtext
✓ **Visual Priority**: At a glance, see importance from bolt count

## Implementation Details

The feature is implemented through:

1. **`detect_priority(message, payload=None)`** - Extracts priority from ntfy JSON payload (1-5 scale)
2. **`get_priority_symbol(priority_level)`** - Returns appropriate symbol and count
3. **Updated `listen()`** - Passes ntfy payload to print_msg with priority
4. **Updated `print_msg()`** - Receives payload and passes priority to create_layout
5. **Updated `create_layout()`** - Renders symbols based on detected priority

All functions are in `app.py` and fully integrated with existing message rendering pipeline.
