#!/bin/bash
# Migration script: safari_start_page → BriefDesk
set -e

echo "🔄 Migrating from safari_start_page to BriefDesk..."
echo ""

OLD_DIR="$HOME/.local/share/safari_start_page"
NEW_DIR="$HOME/.local/share/briefdesk"
LAUNCHAGENTS_DIR="$HOME/Library/LaunchAgents"

# ============================================
# Stop old services
# ============================================
echo "⏹️  Stopping old services..."
launchctl bootout gui/$(id -u)/com.startpage.search 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.startpage.static 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.elias.startpage 2>/dev/null || true
sleep 1

# ============================================
# Migrate data
# ============================================
if [ -d "$OLD_DIR" ]; then
    echo "📁 Migrating data from $OLD_DIR..."
    mkdir -p "$NEW_DIR"
    
    # Copy all files
    cp -r "$OLD_DIR"/* "$NEW_DIR"/ 2>/dev/null || true
    
    # Migrate cache file if exists
    if [ -f "$OLD_DIR/prep_cache.json" ]; then
        cp "$OLD_DIR/prep_cache.json" "$NEW_DIR/"
        echo "   ✓ Migrated prep cache"
    fi
    
    # Migrate config if exists
    if [ -f "$OLD_DIR/config.json" ]; then
        cp "$OLD_DIR/config.json" "$NEW_DIR/"
        echo "   ✓ Migrated config"
    fi
    
    # Migrate Google credentials
    if [ -f "$OLD_DIR/google_credentials.json" ]; then
        cp "$OLD_DIR/google_credentials.json" "$NEW_DIR/"
        echo "   ✓ Migrated Google credentials"
    fi
    if [ -f "$OLD_DIR/token.pickle" ]; then
        cp "$OLD_DIR/token.pickle" "$NEW_DIR/"
        echo "   ✓ Migrated Google token"
    fi
    
    # Migrate devsai config
    if [ -f "$OLD_DIR/.devsai.json" ]; then
        cp "$OLD_DIR/.devsai.json" "$NEW_DIR/"
        echo "   ✓ Migrated devsai config"
    fi
    
    echo "   ✓ Data migration complete"
else
    echo "   ℹ️  No old installation found at $OLD_DIR"
fi

# ============================================
# Remove old LaunchAgents
# ============================================
echo ""
echo "🗑️  Removing old LaunchAgents..."
rm -f "$LAUNCHAGENTS_DIR/com.startpage.search.plist" 2>/dev/null || true
rm -f "$LAUNCHAGENTS_DIR/com.startpage.static.plist" 2>/dev/null || true
rm -f "$LAUNCHAGENTS_DIR/com.elias.startpage.plist" 2>/dev/null || true
echo "   ✓ Old LaunchAgents removed"

# ============================================
# Run new installer
# ============================================
echo ""
echo "📦 Running BriefDesk installer..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/install.sh"

# ============================================
# Optional: Remove old directory
# ============================================
echo ""
if [ -d "$OLD_DIR" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🗑️  Old installation directory still exists at:"
    echo "    $OLD_DIR"
    echo ""
    echo "You can remove it manually after verifying everything works:"
    echo "    rm -rf $OLD_DIR"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

echo ""
echo "✅ Migration complete!"
echo ""
echo "Note: You may need to update Full Disk Access permissions for:"
echo "  $NEW_DIR/python3"
