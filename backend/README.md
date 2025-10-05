# BrainRot Monitor Backend

Clean, minimal backend for detecting scrolling behavior on short-form video platforms.

## Structure

```
backend/
├── server.py           # Main FastAPI app & endpoints
├── ws_manager.py       # WebSocket connection handling
├── dashboard.py        # Web UI HTML
└── detection/
    ├── scroll.py       # Scroll detection (perceptual hashing)
    └── app.py          # App detection (OCR + aspect ratio)
```

## How It Works

1. **Frame Upload**: iOS app sends video frames to `/upload`
2. **App Detection**: Identifies platform (TikTok, Instagram, YouTube, etc.)
3. **Scroll Detection**: Compares frames using perceptual hashing
4. **Dashboard**: Real-time visualization via WebSocket

## Key Features

- **Scroll Detection**: Uses perceptual hashing (8x8 grayscale comparison)
  - Detects content changes between 15-35 bits difference
  - 2.5 second debounce to prevent false positives
- **App Detection**: OCR keyword matching with fallback to aspect ratio

- **Minimal State**: Only tracks current session, frame count, and last hash

## Running

```bash
python server.py
```

Then open the dashboard at `http://localhost:8000`

## Adding Features

The modular structure makes it easy to extend:

- Add new detection algorithms in `detection/`
- Modify UI in `dashboard.py`
- Add new endpoints in `server.py`
