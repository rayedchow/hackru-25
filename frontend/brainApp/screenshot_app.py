#!/usr/bin/env python3
"""
Simple screenshot app - Command+J to select region and send to Electron app
"""

import os
import subprocess
import sys
import time
from contextlib import suppress
from io import BytesIO

import requests
from pynput import keyboard
from pynput.keyboard import Key, KeyCode


class ScreenshotApp:
    def __init__(self):
        self.current_keys = set()
        self.running = True
        self.electron_process = None
        self.web_dir = os.path.join(os.path.dirname(__file__), "web")
        self.taking_screenshot = False  # Prevent multiple simultaneous screenshots

    def on_press(self, key):
        """Handle key press events"""
        self.current_keys.add(key)

        # Check for Command + J
        if (
            Key.cmd in self.current_keys
            and KeyCode.from_char("j") in self.current_keys
            and not self.taking_screenshot
        ):
            print("Command+J detected! Opening macOS region selector...")
            self.taking_screenshot = True
            try:
                self.take_region_screenshot()
            finally:
                self.taking_screenshot = False

    def on_release(self, key):
        """Handle key release events"""
        with suppress(KeyError):
            self.current_keys.remove(key)

    def ensure_electron_running(self):
        """Ensure Electron app is running, launch if not"""
        try:
            # Check if Electron control server is responding
            requests.get("http://127.0.0.1:3001/electron/show", timeout=1)
            print("Electron app already running")
            return True
        except requests.RequestException:
            print("Launching Electron app...")
            try:
                # Launch Electron in background
                self.electron_process = subprocess.Popen(
                    ["npm", "run", "electron-dev"],
                    cwd=self.web_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                # Wait for Electron to be ready (up to 10 seconds)
                for _ in range(20):
                    time.sleep(0.5)
                    try:
                        requests.get("http://127.0.0.1:3001/electron/show", timeout=1)
                        print("Electron app launched successfully!")
                        return True
                    except requests.RequestException:
                        continue

                print("Warning: Electron app may not be ready yet")
                return True
            except OSError as error:
                print(f"Failed to launch Electron app: {error}")
                return False

    def take_region_screenshot(self):
        """Use macOS screencapture to select region and send to Electron app"""
        # `-` sends PNG bytes to stdout, so no plaintext screenshot is written to disk.
        try:
            result = subprocess.run(
                ["screencapture", "-i", "-t", "png", "-"],
                capture_output=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            print("Screenshot selection was unavailable or timed out")
            return

        if result.returncode == 0 and result.stdout:
            try:
                # Send an in-memory stream to the local Next.js adapter.
                files = {"image": ("screenshot.png", BytesIO(result.stdout), "image/png")}
                response = requests.post(
                    "http://127.0.0.1:3000/api/screenshot",
                    files=files,
                    timeout=15,
                )

                if response.status_code == 200:
                    print("Screenshot encrypted and queued locally!")
                    try:
                        requests.post("http://127.0.0.1:3001/electron/show", timeout=1)
                        print("Electron window activated")
                    except requests.RequestException:
                        print("Warning: Could not focus Electron window")
                else:
                    print(f"Failed to queue screenshot: {response.status_code}")
            except requests.exceptions.ConnectionError:
                print("Error: Could not connect to app")
            except requests.Timeout:
                print("Error: Local screenshot ingestion timed out")
        else:
            print("Screenshot canceled")

    def start(self):
        """Start the app"""
        print("Screenshot app starting...")
        print("Launching Electron app in background...")

        # Launch Electron immediately but it stays hidden
        if not self.ensure_electron_running():
            print("Warning: Failed to launch Electron app")
        else:
            print("Electron app ready (hidden in background)")

        print("\nPress Command + J to select region and capture")
        print("Electron will appear when you take a screenshot")
        print("Press Ctrl+C to exit\n")

        listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        listener.start()

        try:
            while self.running:
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nExiting...")
            self.running = False
        finally:
            listener.stop()
            # Kill Electron if we launched it
            if self.electron_process:
                print("Stopping Electron app...")
                self.electron_process.terminate()
                try:
                    self.electron_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.electron_process.kill()
            sys.exit(0)


if __name__ == "__main__":
    app = ScreenshotApp()
    app.start()
