# Receipt Printer - Usage Examples

## Basic Plain Text Messages

### Simple Text
Send a plain string to your ntfy topic:

```bash
curl -d "Hello World" https://ntfy.example.com/my-topic
```

### Text with Subtext
Use JSON payload with `type: "text_with_subtext"`:

```bash
curl -X POST https://ntfy.example.com/my-topic \
  -H "Content-Type: application/json" \
  -d '{
    "type": "text_with_subtext",
    "message": "MEETING REMINDER",
    "subtext": "Conference Room 2 @ 3PM"
  }'
```

Output:
```
     🍆              ← Alert symbol (eggplant emoji)

MEETING REMINDER     ← Main text (70pt bold)

Conference Room 2... ← Subtext (24pt gray)
    @ 3PM

─────────────────    ← Divider

Feb 14, 2025         ← Date
10:30:15             ← Time
```

## Structured JSON Payloads

### Monday.com Kanban Card
For automation via n8n/zapier:

```json
{
  "type": "monday_task",
  "task": "Design homepage mockups",
  "priority": "high",
  "status": "in_progress",
  "assignee": "JD",
  "due_date": "2026-02-15",
  "id": "M123",
  "qr_url": "https://monday.com/boards/123/tasks/456"
}
```

Post via curl:
```bash
curl -X POST https://ntfy.example.com/my-topic \
  -H "Content-Type: application/json" \
  -d '{
    "type": "monday_task",
    "task": "Design homepage mockups",
    "priority": "high",
    "status": "in_progress",
    "assignee": "JD",
    "due_date": "2026-02-15",
    "id": "M123",
    "qr_url": "https://monday.com/boards/123/tasks/456"
  }'
```

Output:
```
┌────────────────────┐
█ Design homepage    │   ← Priority bar (thickness = priority)
│ mockups            │   ← Task title
├────────────────────┤
│ [WIP] [!!]         │   ← Status and priority icons
│ JD | 2026-02-15    │   ← Assignee and due date
│ M123               │   ← Reference ID
│            [QR]    │   ← QR code (70x70px)
└────────────────────┘
```

### Priority Alert with Banner
Visual indicators for urgent alerts:

```json
{
  "type": "priority_alert",
  "priority": "critical",
  "message": "SYSTEM DOWN",
  "subtext": "Database server unreachable"
}
```

Priority levels:
- **critical**: Red background with dense hatching pattern
- **high**: Orange background with medium pattern
- **medium**: Yellow background with light pattern
- **low**: Light green background

## Emoji Handling

The printer automatically converts emoji to ASCII alternatives:

| Emoji | Output | Use Case |
|-------|--------|----------|
| 🍕 | [pizza] | Food delivery |
| 🍔 | [burger] | Food delivery |
| 🍆 | [eggplant] | Alert symbol |
| ☕ | [coffee] | Break notification |
| ✅ | [check] | Completed item |
| ❌ | [x] | Failed item |
| ⚠️ | [warn] | Warning |
| 🔔 | [bell] | Notification |
| 📅 | [cal] | Date-related |
| ⏰ | [clock] | Time-related |
| 👍 | [+1] | Approval |
| 👎 | [-1] | Disapproval |
| ❤️ | [heart] | Appreciation |
| 🔥 | [fire] | Important |
| 💡 | [idea] | Suggestion |
| 📧 | [mail] | Email |
| 📱 | [phone] | Contact |
| 🚨 | [alert] | Emergency |
| ✨ | [*] | Special |

Example:
```bash
curl -d "Pizza 🍕 delivery arrived! ✅" https://ntfy.example.com/my-topic
```

Prints as:
```
     🍆

Pizza [pizza] delivery
arrived! [check]
```

## n8n / Zapier Integration

### Create Kanban Card from Monday.com
**Trigger**: Monday.com task created/updated
**Action**: Send HTTP POST to ntfy with kanban payload

Webhook URL: `https://ntfy.example.com/my-topic`

Body Template:
```json
{
  "type": "monday_task",
  "task": "{{task_name}}",
  "priority": "{{priority}}",
  "status": "{{status}}",
  "assignee": "{{assignee_name}}",
  "due_date": "{{due_date}}",
  "id": "{{task_id}}",
  "qr_url": "{{task_url}}"
}
```

### Create Alert from Monitoring System
**Trigger**: Uptime monitor detects downtime
**Action**: Send priority alert

```json
{
  "type": "priority_alert",
  "priority": "critical",
  "message": "SERVICE DEGRADATION",
  "subtext": "{{service_name}} - {{error_code}}"
}
```

### Delivery Notification
**Trigger**: Package tracking update
**Action**: Send notification with location

```json
{
  "type": "text_with_subtext",
  "message": "DELIVERY UPDATE",
  "subtext": "{{location}} - {{status}}"
}
```

## CLI Testing

### Preview Mode (no printer needed)
```bash
# Test example text
python app.py --preview --example text

# Test kanban card
python app.py --preview --example kanban

# Test custom message with subtext (requires code modification)
```

### Test Alignment
For calibration on new printer:
```bash
python app.py --test-align
```

Prints a grid to verify X/Y offsets and printable width.

## Customization

### Paper Size Configuration
Edit `.env`:
```bash
PAPER_WIDTH_MM=80      # 80mm or 58mm
PRINTER_DPI=203        # 203 DPI for most thermal printers
SAFE_MARGIN_MM=4.0     # Safe printable area margin
```

### Font Sizes
Modify `app.py` constants:
```python
# Plain text layout
font_main_size = 70    # Main message
font_sub_size = 35     # Date/time footer
font_subtext_size = 24 # Optional subtext

# Kanban card layout
font_title = 28        # Task name
font_meta = 16         # Metadata
font_small = 13        # Reference ID
```

### Message Wrapping
```python
MAX_MESSAGE_LENGTH = 300  # Characters before truncation
MAX_LINES = 3             # Lines before truncation
```

## Troubleshooting

### Printer not found
- Verify USB cable is connected
- Check vendor/product IDs: `lsusb`
- Update `.env`:
  ```bash
  PRINTER_VENDOR=0x1234
  PRINTER_PRODUCT=0x5678
  ```

### Text not printing
- Ensure DejaVu fonts installed: `sudo apt install fonts-dejavu-core`
- Check printer has paper/ink

### Emoji appearing as squares
- This is normal! They are automatically converted to ASCII
- To customize emoji mapping, edit `EMOJI_MAP` in `app.py`

### Text cut off at right edge
- Adjust `SAFE_MARGIN_MM` in `.env`
- Run `--test-align` to verify alignment
- Use `X_OFFSET_MM` to shift content left/right

### Service not starting
```bash
# Check status
sudo systemctl status receipt-printer

# View logs
sudo journalctl -u receipt-printer -f
```
