# Rust Overlay Suite

A modular overlay toolkit for Rust. Each module runs independently
and can be toggled on/off from the launcher without restarting.

---

## Folder layout

```
RustOverlay/
├── launcher.py                       ← Run this
├── requirements.txt
├── launcher_config.json              ← Auto-generated on first run
└── modules/
    ├── fight_review.py
    ├── fight_review_config.json      ← Auto-generated
    ├── recoil_control.py
    ├── recoil_config.json            ← Auto-generated
    ├── brightness_control.py
    ├── brightness_config.json        ← Auto-generated
    └── _template_custom_module.py   ← Copy this to make your own
```

---

## Setup

```bash
cd C:\Scripts\Rust\RustOverlay
pip install -r requirements.txt
python launcher.py
```

---

## Modules

### ⚔ Fight Review
Watches your health bar (pixel brightness) and detects:
- Fight start (sudden brightness drop)
- Hits taken (continued drops)
- Death (health near zero)
- Survival (cooldown expires without dying)

A small draggable HUD appears in the top-left of your screen.

**Config** (`modules/fight_review_config.json`):
```json
{
  "health_region": { "left": 1609, "top": 934, "width": 287, "height": 39 },
  "health_drop_threshold": 8,
  "cooldown_seconds": 5,
  "sample_interval": 0.1
}
```
Adjust `health_region` to match your resolution if not 1920×1080.

---

### 🎯 Recoil Control
Applies downward (and optional sideward) mouse movement while left
mouse is held to counteract weapon recoil.

**Default keybinds:**
| Action        | Key |
|---------------|-----|
| Previous profile | F8 |
| Next profile     | F9 |

Rebind at any time via the ⚙ Rebind button on the HUD.

**Weapon groups** (edit `modules/recoil_config.json`):
```json
{
  "groups": [
    {
      "name": "Rifles",
      "profiles": [
        { "name": "AK-47", "x_pull": 0, "y_pull": 5, "tick_ms": 60, "active_button": "right" }
      ]
    }
  ]
}
```
- `y_pull` — pixels to pull down per tick (start at 4–6 for AK)
- `x_pull` — pixels to pull left/right
- `tick_ms` — milliseconds between corrections (match your fire rate)

To add a new group, add an entry to the `groups` array. The HUD
cycles through all profiles across all groups in order.

---

### 🌙 Brightness / Night Vision
Raises system gamma while toggled on. Windows only.

**Default hotkey:** F7 (changeable in the HUD).  
**Boost range:** 1.0 (no change) → 3.0 (very bright).

> **Warning:** Extreme boost (>2.5) may wash out the screen.
> Start at 1.8–2.2 for night visibility without losing detail.

---

## Adding a custom module

1. Copy `modules/_template_custom_module.py` → `modules/my_module.py`
2. Implement `start(stop_event)` and `stop()` at the bottom
3. In the launcher, click **+ Add Custom Module** and browse to your file

Your module is saved across sessions and appears in the launcher list.

---

## Global keybinds

| Key | Action |
|-----|--------|
| F8  | Previous weapon profile (Recoil Control) |
| F9  | Next weapon profile (Recoil Control)     |
| F7  | Toggle Night Vision                       |
| F10 | Stop all modules / exit                   |

All keybinds except F10 are remappable inside each module's HUD.

---

## Disclaimer
This tool reads screen pixels and moves your mouse.
Use responsibly and in accordance with the game's terms of service.