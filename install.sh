#!/bin/bash
set -e

echo "🚀 BriefDesk Installer"
echo "======================"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/.local/share/briefdesk"
LAUNCHAGENTS_DIR="$HOME/Library/LaunchAgents"
DEVSAI_DIR="$HOME/.local/share/devsai"

echo "📁 Creating installation directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$LAUNCHAGENTS_DIR"
mkdir -p "$DEVSAI_DIR"

echo "📄 Copying files..."
cp "$SCRIPT_DIR/start.html" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/search-server.py" "$INSTALL_DIR/"

# Copy example configs if they exist
[ -f "$SCRIPT_DIR/devsai.example.json" ] && cp "$SCRIPT_DIR/devsai.example.json" "$INSTALL_DIR/"
[ -f "$SCRIPT_DIR/config.example.json" ] && cp "$SCRIPT_DIR/config.example.json" "$INSTALL_DIR/"

# ============================================
# Create local Python binary for Full Disk Access
# ============================================
echo ""
echo "🐍 Setting up Python binary for Full Disk Access..."
SYSTEM_PYTHON=$(python3 -c "import sys; print(sys.executable)" 2>/dev/null || echo "/usr/bin/python3")
if [ -f "$SYSTEM_PYTHON" ]; then
    cp "$SYSTEM_PYTHON" "$INSTALL_DIR/python3"
    chmod +x "$INSTALL_DIR/python3"
    echo "   ✓ Copied Python to $INSTALL_DIR/python3"
else
    echo "   ⚠️  Could not find Python binary. You may need to set this up manually."
fi

# ============================================
# Interactive configuration for Hub features
# ============================================
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

    # Auto-detect Google Drive path
    GDRIVE_PATH=""
    if [ -d "$HOME/Library/CloudStorage" ]; then
        # Find the first GoogleDrive folder (most recent if multiple)
        GDRIVE_FOLDER=$(ls -1d "$HOME/Library/CloudStorage/GoogleDrive-"* 2>/dev/null | head -1)
        if [ -n "$GDRIVE_FOLDER" ]; then
            GDRIVE_PATH="$GDRIVE_FOLDER"
            echo "   ✓ Auto-detected Google Drive: $GDRIVE_PATH"
        fi
    fi
    
    if [ -z "$GDRIVE_PATH" ]; then
        echo "   Google Drive path (leave empty to skip):"
        echo "   Example: /Users/you/Library/CloudStorage/GoogleDrive-you@company.com"
        read -r GDRIVE_PATH
    fi

    # Create config file
    cat > "$INSTALL_DIR/config.json" << EOF
{
  "slack_workspace": "$SLACK_WS",
  "atlassian_domain": "$ATLASSIAN_DOMAIN",
  "google_drive_path": "$GDRIVE_PATH"
}
EOF
    echo "   ✓ Configuration saved to $INSTALL_DIR/config.json"
fi

# ============================================
# Install LaunchAgents with local Python
# ============================================
echo ""
echo "⚙️  Installing LaunchAgents..."

# Create static server plist
cat > "$LAUNCHAGENTS_DIR/com.briefdesk.static.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.briefdesk.static</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/python3</string>
        <string>-m</string>
        <string>http.server</string>
        <string>8765</string>
        <string>--bind</string>
        <string>127.0.0.1</string>
        <string>--directory</string>
        <string>$INSTALL_DIR</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/briefdesk-static.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/briefdesk-static.log</string>
</dict>
</plist>
EOF

# Create search server plist
cat > "$LAUNCHAGENTS_DIR/com.briefdesk.server.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.briefdesk.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/python3</string>
        <string>$INSTALL_DIR/search-server.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>SLACK_WORKSPACE</key>
        <string>${SLACK_WS:-your-workspace}</string>
        <key>ATLASSIAN_DOMAIN</key>
        <string>${ATLASSIAN_DOMAIN:-your-domain.atlassian.net}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/briefdesk-server.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/briefdesk-server.log</string>
</dict>
</plist>
EOF

echo "   ✓ LaunchAgents created"

# ============================================
# Start services
# ============================================
echo ""
echo "🔄 Starting services..."
launchctl bootout gui/$(id -u)/com.briefdesk.static 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.briefdesk.server 2>/dev/null || true
# Also remove old startpage services if they exist
launchctl bootout gui/$(id -u)/com.elias.startpage 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.startpage.search 2>/dev/null || true
sleep 1

launchctl bootstrap gui/$(id -u) "$LAUNCHAGENTS_DIR/com.briefdesk.static.plist"
launchctl bootstrap gui/$(id -u) "$LAUNCHAGENTS_DIR/com.briefdesk.server.plist"
sleep 2

# ============================================
# Setup devsai CLI (for Productivity Hub)
# ============================================
echo ""
echo "🤖 Setting up devsai CLI for Productivity Hub..."

# Check if Node.js is installed
if command -v node &> /dev/null; then
    NODE_PATH=$(which node)
    NODE_VERSION=$(node --version)
    echo "   Found Node.js $NODE_VERSION at $NODE_PATH"
    
    # Copy Node binary for FDA
    cp "$NODE_PATH" "$DEVSAI_DIR/node"
    chmod +x "$DEVSAI_DIR/node"
    echo "   ✓ Copied Node to $DEVSAI_DIR/node"
    
    # Check if devsai is installed
    DEVSAI_DIST=""
    if npm list -g devsai &> /dev/null; then
        DEVSAI_DIST=$(npm root -g)/devsai/dist
    elif [ -d "$HOME/Documents/GitHub/devs-ai-cli/dist" ]; then
        # Development install
        DEVSAI_DIST="$HOME/Documents/GitHub/devs-ai-cli/dist"
    fi
    
    if [ -n "$DEVSAI_DIST" ] && [ -d "$DEVSAI_DIST" ]; then
        cp -r "$DEVSAI_DIST" "$DEVSAI_DIR/"
        echo "   ✓ Copied devsai to $DEVSAI_DIR/dist"
    else
        echo "   ℹ️  devsai not found. Install with: npm install -g devsai"
    fi
    
    # Create wrapper script that uses the local Node binary with FDA
    cat > "$DEVSAI_DIR/devsai.sh" << 'EOF'
#!/bin/bash
# Use local Node binary (has Full Disk Access) with local devsai dist
export PATH="$HOME/.nvm/versions/node/$(ls $HOME/.nvm/versions/node 2>/dev/null | tail -1)/bin:$PATH"
exec "$HOME/.local/share/devsai/node" "$HOME/.local/share/devsai/dist/index.js" "$@"
EOF
    chmod +x "$DEVSAI_DIR/devsai.sh"
    echo "   ✓ Created devsai wrapper at $DEVSAI_DIR/devsai.sh"
else
    echo "   ⚠️  Node.js not found. Hub features require Node.js."
    echo "      Install with: brew install node"
fi

# ============================================
# Success message and next steps
# ============================================
echo ""
echo "✅ Installation complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 REQUIRED: Grant Full Disk Access"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Open: System Settings → Privacy & Security → Full Disk Access"
echo ""
echo "Add these binaries (use Cmd+Shift+G to paste paths):"
echo ""
echo "  1. $INSTALL_DIR/python3"
echo "     (Required for Safari history search)"
echo ""
if [ -f "$DEVSAI_DIR/node" ]; then
echo "  2. $DEVSAI_DIR/node"
echo "     (Required for Google Drive search in Hub)"
echo ""
fi
echo "After adding, restart the services:"
echo "  launchctl kickstart -k gui/\$(id -u)/com.briefdesk.server"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Set Browser Homepage"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Safari → Settings → General"
echo "  Homepage: http://127.0.0.1:8765/start.html"
echo "  New windows/tabs open with: Homepage"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📚 Hub Features (Optional)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "For Jira, Confluence, Slack, Gmail, Drive integrations:"
echo ""
echo "1. Install devsai CLI:"
echo "   npm install -g devsai"
echo ""
echo "2. Configure MCP servers:"
echo "   cp $INSTALL_DIR/devsai.example.json $INSTALL_DIR/.devsai.json"
echo "   Edit $INSTALL_DIR/.devsai.json with your credentials"
echo ""
echo "3. Install MCP servers globally (for faster startup):"
echo "   npm install -g slack-mcp-server mcp-remote @anthropic/gmail-mcp-server"
echo ""
echo "See README.md for detailed Hub setup and credential instructions."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 After Updating devsai CLI"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "If you update devsai (npm install -g devsai), re-copy the dist:"
echo "  cp -r \$(npm root -g)/devsai/dist ~/.local/share/devsai/"
echo ""
echo "Or re-run this install script."
echo ""
echo "🔗 Open: http://127.0.0.1:8765/start.html"
