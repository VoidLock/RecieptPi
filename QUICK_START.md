# Quick Reference: New Features

## Feature 1: Plain Text with Subtext

### Python API
```python
from app import WhiteboardPrinter

wp = WhiteboardPrinter()
wp.print_msg("MAIN MESSAGE", subtext="Secondary message")
```

### ntfy JSON Payload
```json
{
  "type": "text_with_subtext",
  "message": "MAIN MESSAGE",
  "subtext": "Secondary message"
}
```

### Examples
```bash
# Delivery notification
curl -d '{
  "type": "text_with_subtext",
  "message": "PACKAGE DELIVERED",
  "subtext": "Dock 2 - Sign here"
}' https://ntfy.example.com/my-topic

# Meeting reminder
curl -d '{
  "type": "text_with_subtext",
  "message": "MEETING STARTING",
  "subtext": "Conference Room B - Dial in info sent"
}' https://ntfy.example.com/my-topic
```

---

## Feature 2: Priority Banners

### JSON Payload
```json
{
  "type": "priority_alert",
  "priority": "critical",
  "message": "ALERT TEXT",
  "subtext": "Details (optional)"
}
```

### Priority Levels
| Priority | Visual | Use Case |
|----------|--------|----------|
| `critical` | Red banner + dense hatching | System down, emergency |
| `high` | Orange banner + medium hatching | Urgent action needed |
| `medium` | Yellow banner + light hatching | Important notice |
| `low` | Light green banner | FYI notifications |

### Examples
```bash
# Critical system alert
curl -d '{
  "type": "priority_alert",
  "priority": "critical",
  "message": "DATABASE OFFLINE",
  "subtext": "Production environment - Page 911 Team"
}' https://ntfy.example.com/my-topic

# Medium priority maintenance
curl -d '{
  "type": "priority_alert",
  "priority": "medium",
  "message": "MAINTENANCE WINDOW",
  "subtext": "Scheduled 2:00 AM - 30 min downtime"
}' https://ntfy.example.com/my-topic

# Low priority info
curl -d '{
  "type": "priority_alert",
  "priority": "low",
  "message": "NEW EMPLOYEE ONBOARD",
  "subtext": "John Doe - Welcome to team!"
}' https://ntfy.example.com/my-topic
```

---

## Existing Features (Still Available)

### Plain Text (backward compatible)
```bash
curl -d "Simple message" https://ntfy.example.com/my-topic
```

### Monday.com Kanban Cards
```json
{
  "type": "monday_task",
  "task": "Task name",
  "priority": "high",
  "status": "in_progress",
  "assignee": "JD",
  "due_date": "2026-02-28",
  "id": "TASK-123",
  "qr_url": "https://monday.com/..."
}
```

---

## Testing

### Test in Preview Mode (No Printer Needed)
```bash
# Test plain text examples
python app.py --preview --example text

# Test kanban card
python app.py --preview --example kanban

# Test custom messages with Python
python3 << 'EOF'
import json
from app import WhiteboardPrinter

wp = WhiteboardPrinter(preview_mode=True)

# Test subtext
wp.print_msg("DEMO MESSAGE", subtext="This is secondary text")

# Test priority alert
wp.print_msg(json.dumps({
  "type": "priority_alert",
  "priority": "critical",
  "message": "TEST ALERT"
}))
EOF
```

---

## Integration Examples

### n8n: Monday.com → Printer
**Trigger**: Monday.com task created
**Webhook**: POST to ntfy

Body template:
```json
{
  "type": "monday_task",
  "task": "{{task_name}}",
  "priority": "{{priority}}",
  "status": "{{status}}",
  "assignee": "{{assignee_name}}",
  "due_date": "{{due_date}}",
  "id": "{{task_id}}",
  "qr_url": "{{board_url}}"
}
```

### Zapier: Uptime Monitor → Alert
**Trigger**: Service down alert
**Action**: Webhook to ntfy

```json
{
  "type": "priority_alert",
  "priority": "critical",
  "message": "SERVICE DOWN",
  "subtext": "{{service_name}} - {{status_page_url}}"
}
```

### Home Automation: Smart Home → Alerts
Send ntfy payload when alarm triggers:
```json
{
  "type": "priority_alert",
  "priority": "critical",
  "message": "⚠ ALARM TRIGGERED",
  "subtext": "{{location}} - {{timestamp}}"
}
```

---

## Emoji Mapping (Auto-converted)

Common emoji are automatically converted to ASCII alternatives:

| Input | Prints As | Use Case |
|-------|-----------|----------|
| 🍕 | [pizza] | Food delivery |
| 🍔 | [burger] | Food delivery |
| ☕ | [coffee] | Break time |
| ✅ | [check] | Completed |
| ❌ | [x] | Failed |
| ⚠️ | [warn] | Warning |
| 🔔 | [bell] | Notification |
| 📅 | [cal] | Date |
| ⏰ | [clock] | Time |
| 🔥 | [fire] | Important |
| 💡 | [idea] | Suggestion |

Example:
```bash
curl -d '{
  "type": "text_with_subtext",
  "message": "Pizza 🍕 Delivered",
  "subtext": "Check ✅ your order"
}' https://ntfy.example.com/my-topic
```

Prints as:
```
PIZZA [pizza] DELIVERED
Check [check] your order
```

---

## Troubleshooting

### Message not appearing
- Check ntfy connection: `curl https://ntfy.example.com/your-topic`
- Verify systemd service: `sudo systemctl status receipt-printer`
- Check logs: `sudo journalctl -u receipt-printer -f`

### Text cut off
- Adjust margins: Edit `SAFE_MARGIN_MM` in `.env`
- Test alignment: `python app.py --test-align`

### Subtext not showing
- Ensure DejaVu fonts: `sudo apt install fonts-dejavu-core`
- Test with preview mode first

### Priority banners not rendering
- Verify JSON format includes all required fields
- Check priority value is one of: critical, high, medium, low
- Test with `--preview` mode

---

## Configuration

### .env Variables
```bash
# ntfy settings
NTFY_HOST=https://ntfy.example.com
NTFY_TOPIC=my-topic

# Printer settings
PAPER_WIDTH_MM=80              # 80mm or 58mm
PRINTER_DPI=203
X_OFFSET_MM=0                  # Horizontal offset
Y_OFFSET_MM=0                  # Vertical offset
SAFE_MARGIN_MM=4.0             # Safe printable area

# Memory settings
MEM_THRESHOLD_PERCENT=80       # Pause printing
MEM_RESUME_PERCENT=70          # Resume printing

# Message settings
MAX_MESSAGE_LENGTH=300
MAX_LINES=3
```

---

## System Requirements

- Python 3.8+
- PIL/Pillow (image rendering)
- escpos (printer commands)
- DejaVu fonts installed
- USB thermal printer (ESC/POS compatible)

Install fonts:
```bash
sudo apt install fonts-dejavu-core
```
