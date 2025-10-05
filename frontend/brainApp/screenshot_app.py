#!/usr/bin/env python3
"""
Simple screenshot app - Command+J to select region and send to Electron app
"""

from pynput import keyboard
from pynput.keyboard import Key, KeyCode
import subprocess
import time
import sys
import requests
import os


class ScreenshotApp:
    def __init__(self):
        self.current_keys = set()
        self.running = True
        self.electron_process = None
        self.web_dir = os.path.join(os.path.dirname(__file__), 'web')
        self.taking_screenshot = False  # Prevent multiple simultaneous screenshots
        
    def on_press(self, key):
        """Handle key press events"""
        self.current_keys.add(key)
        
        # Check for Command + J
        if (Key.cmd in self.current_keys and 
            KeyCode.from_char('j') in self.current_keys and
            not self.taking_screenshot):
            print("Command+J detected! Opening macOS region selector...")
            self.taking_screenshot = True
            self.take_region_screenshot()
            self.taking_screenshot = False
    
    def on_release(self, key):
        """Handle key release events"""
        try:
            self.current_keys.remove(key)
        except KeyError:
            pass
    
    def ensure_electron_running(self):
        """Ensure Electron app is running, launch if not"""
        try:
            # Check if Electron control server is responding
            requests.get('http://localhost:3001/electron/show', timeout=1)
            print("Electron app already running")
            return True
        except:
            print("Launching Electron app...")
            try:
                # Launch Electron in background
                self.electron_process = subprocess.Popen(
                    ['npm', 'run', 'electron-dev'],
                    cwd=self.web_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                # Wait for Electron to be ready (up to 10 seconds)
                for _ in range(20):
                    time.sleep(0.5)
                    try:
                        requests.get('http://localhost:3001/electron/show', timeout=1)
                        print("Electron app launched successfully!")
                        return True
                    except:
                        continue
                
                print("Warning: Electron app may not be ready yet")
                return True
            except Exception as e:
                print(f"Failed to launch Electron app: {e}")
                return False
    
    def take_region_screenshot(self):
        """Use macOS screencapture to select region and send to Electron app"""
        temp_path = '/tmp/screenshot.png'
        
        # -i = interactive selection
        result = subprocess.run(['screencapture', '-i', temp_path])
        
        if result.returncode == 0:
            # Check if file was created (user didn't cancel)
            try:
                with open(temp_path, 'rb') as f:
                    # Send to Next.js API
                    files = {'image': ('screenshot.png', f, 'image/png')}
                    response = requests.post('http://localhost:3000/api/screenshot', files=files)
                    
                    if response.status_code == 200:
                        print("Screenshot uploaded!")
                        
                        # Tell Electron to show and focus window
                        try:
                            requests.post('http://localhost:3001/electron/show', timeout=1)
                            print("Electron window activated")
                        except:
                            print("Warning: Could not focus Electron window")
                        
                        print("got here")
                    else:
                        print(f"Failed to upload screenshot: {response.status_code}")
            except FileNotFoundError:
                print("Screenshot canceled")
            except requests.exceptions.ConnectionError:
                print("Error: Could not connect to app")
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
        
        listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
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
                except:
                    self.electron_process.kill()
            sys.exit(0)


if __name__ == "__main__":
    app = ScreenshotApp()
    app.start()
