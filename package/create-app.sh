#!/bin/bash
# Creates a macOS .app bundle for BriefDesk with native GUI installer wizard

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
APP_NAME="BriefDesk"
APP_DIR="$SCRIPT_DIR/$APP_NAME.app"
VERSION="1.0.0"

echo "📦 Creating BriefDesk.app..."

# Clean up old build
rm -rf "$APP_DIR"

# Create app bundle structure
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Create the main executable that runs installation then opens installer wizard
cat > "$APP_DIR/Contents/MacOS/BriefDesk" << 'LAUNCHER'
#!/bin/bash

# Get the Resources directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCES_DIR="$SCRIPT_DIR/../Resources"

# Installation paths
INSTALL_DIR="$HOME/.local/share/briefdesk"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/css"
mkdir -p "$INSTALL_DIR/js"
mkdir -p "$INSTALL_DIR/lib"
mkdir -p "$LAUNCH_AGENTS_DIR"

# Copy files
cp "$RESOURCES_DIR/start.html" "$INSTALL_DIR/"
cp "$RESOURCES_DIR/setup.html" "$INSTALL_DIR/"
cp "$RESOURCES_DIR/installer.html" "$INSTALL_DIR/"
cp "$RESOURCES_DIR/search-server.py" "$INSTALL_DIR/"
cp "$RESOURCES_DIR/search-service.mjs" "$INSTALL_DIR/"
cp -r "$RESOURCES_DIR/css/"* "$INSTALL_DIR/css/"
cp -r "$RESOURCES_DIR/js/"* "$INSTALL_DIR/js/"
cp -r "$RESOURCES_DIR/lib/"* "$INSTALL_DIR/lib/"

# Copy config examples (don't overwrite existing)
[ ! -f "$INSTALL_DIR/config.json" ] && [ -f "$RESOURCES_DIR/config.example.json" ] && cp "$RESOURCES_DIR/config.example.json" "$INSTALL_DIR/config.json"
[ ! -f "$INSTALL_DIR/.devsai.json" ] && [ -f "$RESOURCES_DIR/devsai.example.json" ] && cp "$RESOURCES_DIR/devsai.example.json" "$INSTALL_DIR/.devsai.json"

# Create LaunchAgents
cat > "$LAUNCH_AGENTS_DIR/com.briefdesk.static.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.briefdesk.static</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>http.server</string>
        <string>8765</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/briefdesk-static.log</string>
    <key>StandardOutPath</key>
    <string>/tmp/briefdesk-static.log</string>
</dict>
</plist>
PLIST

cat > "$LAUNCH_AGENTS_DIR/com.briefdesk.server.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.briefdesk.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$INSTALL_DIR/search-server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/briefdesk-server.log</string>
    <key>StandardOutPath</key>
    <string>/tmp/briefdesk-server.log</string>
</dict>
</plist>
PLIST

# Find Node.js path
NODE_PATH="/usr/local/bin/node"
[ -f "/opt/homebrew/bin/node" ] && NODE_PATH="/opt/homebrew/bin/node"

cat > "$LAUNCH_AGENTS_DIR/com.briefdesk.search-service.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.briefdesk.search-service</string>
    <key>ProgramArguments</key>
    <array>
        <string>$NODE_PATH</string>
        <string>$INSTALL_DIR/search-service.mjs</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/briefdesk-search-service.log</string>
    <key>StandardOutPath</key>
    <string>/tmp/briefdesk-search-service.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>$HOME</string>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
PLIST

# Load LaunchAgents (unload first to refresh)
launchctl unload "$LAUNCH_AGENTS_DIR/com.briefdesk.static.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.briefdesk.server.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.briefdesk.search-service.plist" 2>/dev/null || true

launchctl load "$LAUNCH_AGENTS_DIR/com.briefdesk.static.plist"
launchctl load "$LAUNCH_AGENTS_DIR/com.briefdesk.server.plist"
launchctl load "$LAUNCH_AGENTS_DIR/com.briefdesk.search-service.plist"

# Wait for servers to start
sleep 2

# Open the installer wizard
for i in {1..15}; do
    if curl -s http://127.0.0.1:18765/debug > /dev/null 2>&1; then
        open "http://127.0.0.1:8765/installer.html"
        exit 0
    fi
    sleep 1
done

# Fallback - open anyway
open "http://127.0.0.1:8765/installer.html"
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/BriefDesk"

# Create Info.plist
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>BriefDesk</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.briefdesk.app</string>
    <key>CFBundleName</key>
    <string>BriefDesk</string>
    <key>CFBundleDisplayName</key>
    <string>BriefDesk</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# Copy project files to Resources
echo "📄 Copying project files..."
cp "$PROJECT_DIR/start.html" "$APP_DIR/Contents/Resources/"
cp "$PROJECT_DIR/setup.html" "$APP_DIR/Contents/Resources/"
cp "$PROJECT_DIR/installer.html" "$APP_DIR/Contents/Resources/"
cp "$PROJECT_DIR/search-server.py" "$APP_DIR/Contents/Resources/"
cp "$PROJECT_DIR/search-service.mjs" "$APP_DIR/Contents/Resources/"
cp -r "$PROJECT_DIR/lib" "$APP_DIR/Contents/Resources/"
cp -r "$PROJECT_DIR/css" "$APP_DIR/Contents/Resources/"
cp -r "$PROJECT_DIR/js" "$APP_DIR/Contents/Resources/"

# Copy example configs if they exist
[ -f "$PROJECT_DIR/devsai.example.json" ] && cp "$PROJECT_DIR/devsai.example.json" "$APP_DIR/Contents/Resources/"
[ -f "$PROJECT_DIR/config.example.json" ] && cp "$PROJECT_DIR/config.example.json" "$APP_DIR/Contents/Resources/"

echo "✅ Created: $APP_DIR"
echo ""
echo "To test: open \"$APP_DIR\""
echo "To create a DMG: ./create-dmg.sh"
