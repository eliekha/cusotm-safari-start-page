#!/bin/bash
# Creates a macOS .app bundle for BriefDesk Installer

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
APP_NAME="BriefDesk Installer"
APP_DIR="$SCRIPT_DIR/$APP_NAME.app"
VERSION="1.0.0"

echo "📦 Creating BriefDesk Installer.app..."

# Clean up old build
rm -rf "$APP_DIR"

# Create app bundle structure
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Create the launcher script
cat > "$APP_DIR/Contents/MacOS/BriefDesk Installer" << 'LAUNCHER'
#!/bin/bash
# BriefDesk Installer Launcher

# Get the Resources directory
RESOURCES_DIR="$(dirname "$0")/../Resources"

# Run the install script
osascript -e "tell application \"Terminal\" to do script \"cd '$RESOURCES_DIR' && ./install.sh && exit\""

# Wait a moment then open setup page
sleep 8

# Check if servers are ready
for i in {1..30}; do
    if curl -s http://127.0.0.1:18765/debug > /dev/null 2>&1; then
        open "http://127.0.0.1:8765/setup.html"
        exit 0
    fi
    sleep 1
done

# If servers didn't start, still open setup (it will show error)
open "http://127.0.0.1:8765/setup.html"
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/BriefDesk Installer"

# Create Info.plist
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>BriefDesk Installer</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.briefdesk.installer</string>
    <key>CFBundleName</key>
    <string>BriefDesk Installer</string>
    <key>CFBundleDisplayName</key>
    <string>BriefDesk Installer</string>
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
cp "$PROJECT_DIR/install.sh" "$APP_DIR/Contents/Resources/"
cp "$PROJECT_DIR/start.html" "$APP_DIR/Contents/Resources/"
cp "$PROJECT_DIR/setup.html" "$APP_DIR/Contents/Resources/"
cp "$PROJECT_DIR/search-server.py" "$APP_DIR/Contents/Resources/"
cp "$PROJECT_DIR/search-service.mjs" "$APP_DIR/Contents/Resources/"
cp -r "$PROJECT_DIR/lib" "$APP_DIR/Contents/Resources/"
cp -r "$PROJECT_DIR/css" "$APP_DIR/Contents/Resources/"
cp -r "$PROJECT_DIR/js" "$APP_DIR/Contents/Resources/"
cp -r "$PROJECT_DIR/launchagents" "$APP_DIR/Contents/Resources/"

# Copy example configs if they exist
[ -f "$PROJECT_DIR/devsai.example.json" ] && cp "$PROJECT_DIR/devsai.example.json" "$APP_DIR/Contents/Resources/"
[ -f "$PROJECT_DIR/config.example.json" ] && cp "$PROJECT_DIR/config.example.json" "$APP_DIR/Contents/Resources/"

# Create a simple icon (optional - can be replaced with proper .icns)
# For now, we'll skip this as it requires additional tools

echo "✅ Created: $APP_DIR"
echo ""
echo "To create a DMG, run: ./create-dmg.sh"
