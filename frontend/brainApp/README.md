# Brain App - Screenshot Capture Tool

A Python background application that captures screenshots using a global hotkey.

## Features

- Global hotkey: **Command + Option + L** to trigger screenshot
- Displays captured screenshot in a window
- Simple "OK" button to confirm
- Runs in the background

## Setup

1. Install Python 3.8 or higher (if not already installed)

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. **Important for macOS**: Grant accessibility permissions
   - Go to System Preferences → Security & Privacy → Privacy → Accessibility
   - Add Terminal (or your Python executable) to the list of allowed apps

## Usage

Run the app:

```bash
python screenshot_app.py
```

Once running:

1. Press **Command + Option + L** to capture a screenshot
2. The screenshot will appear in a window
3. Click "OK" to confirm (prints "got here")
4. Press **Ctrl+C** in the terminal to exit the app

## Requirements

- Python 3.8+
- macOS (uses Command key)
- Accessibility permissions for keyboard monitoring


