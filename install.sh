#!/bin/bash
set -e

echo "🚀 Safari Start Page Installer"
echo "==============================="
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/.local/share/safari_start_page"
LAUNCHAGENTS_DIR="$HOME/Library/LaunchAgents"

echo "📁 Creating installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$LAUNCHAGENTS_DIR"

echo "📄 Copying files..."
cp "$SCRIPT_DIR/start.html" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/search-server.py" "$INSTALL_DIR/"

# Interactive configuration for Hub features
echo ""
echo "⚙️  Hub Configuration (optional - press Enter to skip)"
echo "   These settings are for the Productivity Hub features."
echo ""

# Check if config already exists
if [ -f "$INSTALL_DIR/config.json" ]; then
    echo "   Existing config found. Keep current settings? [Y/n]"
    read -r KEEP_CONFIG
    if [ "$KEEP_CONFIG" != "n" ] && [ "$KEEP_CONFIG" != "N" ]; then
        echo "   ✓ Keeping existing configuration"
        SKIP_CONFIG=true
    fi
fi

if [ "$SKIP_CONFIG" != "true" ]; then
    # Slack workspace
    echo "   Slack workspace name (e.g., 'mycompany' for mycompany.slack.com):"
    read -r SLACK_WS
    SLACK_WS=${SLACK_WS:-your-workspace}

    # Atlassian domain
    echo "   Atlassian domain (e.g., 'mycompany.atlassian.net'):"
    read -r ATLASSIAN_DOMAIN
    ATLASSIAN_DOMAIN=${ATLASSIAN_DOMAIN:-your-domain.atlassian.net}

    # Create config file
    cat > "$INSTALL_DIR/config.json" << EOF
{
  "slack_workspace": "$SLACK_WS",
  "atlassian_domain": "$ATLASSIAN_DOMAIN"
}
EOF
    echo "   ✓ Configuration saved to $INSTALL_DIR/config.json"
fi

echo ""
echo "⚙️  Installing LaunchAgents..."
for plist in "$SCRIPT_DIR/launchagents/"*.plist; do
    filename=$(basename "$plist")
    sed "s|HOME_DIR|$HOME|g" "$plist" > "$LAUNCHAGENTS_DIR/$filename"
done

echo "🔄 Starting services..."
launchctl bootout gui/$(id -u)/com.startpage.static 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.startpage.search 2>/dev/null || true
sleep 1

launchctl bootstrap gui/$(id -u) "$LAUNCHAGENTS_DIR/com.startpage.static.plist"
launchctl bootstrap gui/$(id -u) "$LAUNCHAGENTS_DIR/com.startpage.search.plist"
sleep 2

echo ""
echo "✅ Installation complete!"
echo ""
echo "📋 Next steps:"
echo ""
echo "1. Grant Full Disk Access to Python (required for Safari history):"
echo "   • Open System Settings → Privacy & Security → Full Disk Access"
echo "   • Click + and add the Python binary:"
echo "     $(/usr/bin/python3 -c 'import sys; print(sys.executable)' 2>/dev/null || echo '/usr/bin/python3')"
echo "   • Then restart the search service:"
echo "     launchctl kickstart -k gui/\$(id -u)/com.startpage.search"
echo ""
echo "2. Set Safari homepage:"
echo "   • Safari → Settings → General"
echo "   • Homepage: http://127.0.0.1:8765/start.html"
echo "   • New windows/tabs open with: Homepage"
echo ""
echo "3. Customize your start page:"
echo "   • Open http://127.0.0.1:8765/start.html"
echo "   • Click the gear icon (bottom-right) to set your name and quick links"
echo ""
echo "🔗 Open: http://127.0.0.1:8765/start.html"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📚 Hub Features (Meeting Prep) - Optional Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "To use the Productivity Hub with Jira, Confluence, Slack, Gmail:"
echo ""
echo "1. Install devsai CLI:  npm install -g devsai"
echo "2. Configure MCP servers in $INSTALL_DIR/.devsai.json"
echo "3. For Gmail: npx @anthropic/gmail-mcp-server auth"
echo ""
echo "See README.md for detailed Hub setup instructions."
