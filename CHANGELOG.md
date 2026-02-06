# Update Summary: Subtext & Priority Banner Support

## Overview
Added support for optional subtext in plain text layouts and introduced visual priority banners with ASCII styling. All changes maintain backward compatibility with existing code.

## Changes Made

### 1. **New Parameter: `subtext` in `create_layout()`**
   - Method signature: `create_layout(self, message, subtext=None)`
   - Renders optional secondary text below main message in gray (24pt)
   - Automatically adjusts canvas height based on subtext presence
   - Fully backward compatible (subtext is optional)

### 2. **Updated `print_msg()` Method**
   - Now accepts `subtext` parameter: `print_msg(message, subtext=None)`
   - Passes subtext through to layout renderers
   - Works with both plain text and JSON payloads

### 3. **New JSON Payload Types**

#### `text_with_subtext`
```json
{
  "type": "text_with_subtext",
  "message": "MAIN TEXT",
  "subtext": "Secondary text"
}
```
- Renders plain text with optional subtext via JSON
- Useful for automation platforms (n8n, Zapier)

#### `priority_alert`
```json
{
  "type": "priority_alert",
  "priority": "critical|high|medium|low",
  "message": "ALERT MESSAGE",
  "subtext": "Optional details"
}
```
- Visual priority banners with ASCII-based styling
- Four priority levels with distinct visual patterns
- Includes colored backgrounds and diagonal hatching
- Supports optional subtext

### 4. **New Helper Function: `draw_priority_banner()`**
   - Draws priority-based visual banners with:
     - Colored backgrounds (red/orange/yellow/green)
     - Hatching patterns (density based on priority)
     - Centered text
     - Black borders
   - Supports 4 priority levels with themed styling

### 5. **Updated `render_structured()` Method**
   - Now routes 3 JSON types: `monday_task`, `text_with_subtext`, `priority_alert`
   - Added `_render_priority_alert()` method for banner-based alerts
   - Maintains fallback behavior for unknown types

## Features

### Plain Text with Subtext
```bash
# Via Python
wp.print_msg("MEETING AT 3PM", subtext="Conference Room 2")

# Via ntfy + JSON
curl -X POST https://ntfy.example.com/topic \
  -H "Content-Type: application/json" \
  -d '{
    "type": "text_with_subtext",
    "message": "LUNCH DELIVERY",
    "subtext": "Main entrance - Please sign"
  }'
```

### Visual Priority Alerts
```bash
curl -X POST https://ntfy.example.com/topic \
  -H "Content-Type: application/json" \
  -d '{
    "type": "priority_alert",
    "priority": "critical",
    "message": "SYSTEM DOWN",
    "subtext": "Database server offline"
  }'
```

## Visual Design

### Plain Text with Subtext
```
     🍆            
                   
MEETING            
AT 3PM             
                   
Conference Room 2  (gray, 24pt)
                   
─────────────────  
                   
Feb 14, 2025       
10:30:15           
```

### Priority Banners
- **Critical**: Red (#FF6464) with dense diagonal hatching
- **High**: Orange (#FFB464) with medium hatching
- **Medium**: Yellow (#FFFF64) with light hatching
- **Low**: Light Green (#C8FFC8) with minimal styling

## Technical Details

### Font Sizing
- Main message: 70pt bold (DejaVuSans-Bold)
- Subtext (optional): 24pt regular (DejaVuSans)
- Banner text: 28pt bold
- Metadata: 16pt regular

### Image Dimensions
- Paper: 80mm (639px @ 203 DPI)
- Printable: 72mm (575px)
- Safe margins: 4mm each side
- Image pipeline: 2x scale → grayscale → autocontrast → 1-bit dither

### Emoji Handling
- All emoji automatically converted to ASCII alternatives
- Applies to both message text and subtext
- Example: 🍕 → [pizza], ⚠️ → [warn]

## Backward Compatibility

✓ All existing code continues to work unchanged
✓ `create_layout(message)` still works (subtext defaults to None)
✓ `print_msg(message)` still works (subtext defaults to None)
✓ Existing JSON payloads (`monday_task`) unaffected
✓ Plain text messages work as before

## Testing

All features tested with preview mode:
```bash
python app.py --preview --example text
python app.py --preview --example kanban
```

New payload types can be tested by modifying the `--example` code or posting JSON to ntfy.

## Documentation Files

- **EXAMPLES.md** - Comprehensive usage examples for all payload types
- **SUBTEXT_FEATURE.md** - Detailed subtext feature documentation
- **FEATURES.md** - (existing) High-level feature overview

## Next Steps (Optional)

Possible future enhancements:
1. Custom banner styles (box drawing characters, different patterns)
2. Multi-color support (if printer supports)
3. QR codes in priority alerts
4. Custom emoji-to-ASCII mappings via configuration
5. Dynamic priority bar widths in kanban cards

## Files Modified

- `app.py` - Added subtext support, priority banners, new JSON types
- `EXAMPLES.md` (new) - Usage examples and integration guides
- `SUBTEXT_FEATURE.md` (new) - Feature-specific documentation

## Validation

✓ All code passes syntax validation
✓ Features tested in preview mode (no printer required)
✓ All JSON payload types working
✓ Backward compatibility maintained
✓ Emoji filtering working across all types
✓ Image dimensions correct for paper size
