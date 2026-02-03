#!/bin/bash
# Creates a .dmg disk image for BriefDesk

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="BriefDesk"
APP_DIR="$SCRIPT_DIR/$APP_NAME.app"
DMG_NAME="BriefDesk"
VERSION="1.0.0"
DMG_PATH="$SCRIPT_DIR/$DMG_NAME-$VERSION.dmg"
TEMP_DMG="$SCRIPT_DIR/temp_$DMG_NAME.dmg"
VOLUME_NAME="BriefDesk"

# Check if app exists
if [ ! -d "$APP_DIR" ]; then
    echo "❌ Error: $APP_DIR not found"
    echo "   Run ./create-app.sh first"
    exit 1
fi

echo "📦 Creating DMG: $DMG_PATH"

# Clean up old DMGs
rm -f "$DMG_PATH" "$TEMP_DMG"

# Create a temporary directory for DMG contents
DMG_TEMP="$SCRIPT_DIR/dmg_temp"
rm -rf "$DMG_TEMP"
mkdir -p "$DMG_TEMP"

# Copy app to temp directory
cp -r "$APP_DIR" "$DMG_TEMP/"

# Create Applications symlink
ln -s /Applications "$DMG_TEMP/Applications"

# Create a README
cat > "$DMG_TEMP/README.txt" << 'README'
BriefDesk Installation
======================

1. Drag "BriefDesk" to Applications
2. Double-click to launch
3. Follow the step-by-step setup wizard

The wizard will help you:
• Install BriefDesk
• Configure Google Calendar
• Connect Slack
• Set up other integrations

After setup, set your browser homepage to:
   http://127.0.0.1:8765/start.html

Note: On first run, you may need to right-click the app
and select "Open" to bypass the unidentified developer warning.
README

# Calculate size needed (add some buffer)
SIZE=$(du -sm "$DMG_TEMP" | cut -f1)
SIZE=$((SIZE + 10))

# Create temporary DMG
echo "   Creating disk image..."
hdiutil create -srcfolder "$DMG_TEMP" -volname "$VOLUME_NAME" -fs HFS+ -fsargs "-c c=64,a=16,e=16" -format UDRW -size ${SIZE}m "$TEMP_DMG"

# Mount it
echo "   Mounting..."
DEVICE=$(hdiutil attach -readwrite -noverify -noautoopen "$TEMP_DMG" | awk '/Apple_HFS/{print $1}')
MOUNT_POINT="/Volumes/$VOLUME_NAME"

# Wait for mount
sleep 2

# Set background and icon positions (optional - requires more setup)
# For now, we'll skip fancy DMG styling

# Unmount
echo "   Finalizing..."
sync
hdiutil detach "$DEVICE" -quiet

# Convert to compressed DMG
hdiutil convert "$TEMP_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"

# Clean up
rm -f "$TEMP_DMG"
rm -rf "$DMG_TEMP"

echo ""
echo "✅ Created: $DMG_PATH"
echo ""
echo "📤 Distribution:"
echo "   - Upload to GitHub Releases"
echo "   - Share direct download link"
echo ""
echo "⚠️  Note: Users will see 'unidentified developer' warning."
echo "   They can bypass by right-clicking → Open"
echo "   (or System Preferences → Security → Open Anyway)"
