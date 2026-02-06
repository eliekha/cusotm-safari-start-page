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
cp "$SCRIPT_DIR/setup.html" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/installer.html" "$INSTALL_DIR/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/icons" "$INSTALL_DIR/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/browser-extension" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/search-server.py" "$INSTALL_DIR/"

# Copy lib modules
if [ -d "$SCRIPT_DIR/lib" ]; then
    cp -r "$SCRIPT_DIR/lib" "$INSTALL_DIR/"
    echo "   ✓ Copied lib/ modules"
fi

# Copy frontend assets
if [ -d "$SCRIPT_DIR/css" ]; then
    cp -r "$SCRIPT_DIR/css" "$INSTALL_DIR/"
    echo "   ✓ Copied css/ folder"
fi
if [ -d "$SCRIPT_DIR/js" ]; then
    cp -r "$SCRIPT_DIR/js" "$INSTALL_DIR/"
    echo "   ✓ Copied js/ folder"
fi

# Copy Node.js search service
if [ -f "$SCRIPT_DIR/search-service.mjs" ]; then
    cp "$SCRIPT_DIR/search-service.mjs" "$INSTALL_DIR/"
    echo "   ✓ Copied search-service.mjs"
fi

# Copy Google Drive MCP
if [ -d "$SCRIPT_DIR/gdrive-mcp" ]; then
    cp -r "$SCRIPT_DIR/gdrive-mcp" "$INSTALL_DIR/"
    echo "   ✓ Copied gdrive-mcp"
fi

# Copy example configs if they exist
[ -f "$SCRIPT_DIR/devsai.example.json" ] && cp "$SCRIPT_DIR/devsai.example.json" "$INSTALL_DIR/"
[ -f "$SCRIPT_DIR/config.example.json" ] && cp "$SCRIPT_DIR/config.example.json" "$INSTALL_DIR/"

# ============================================
# Create Python wrapper for Full Disk Access
# ============================================
echo ""
echo "🐍 Setting up Python for Full Disk Access..."
SYSTEM_PYTHON=$(python3 -c "import sys; print(sys.executable)" 2>/dev/null || echo "/usr/bin/python3")
if [ -f "$SYSTEM_PYTHON" ]; then
    # Create a wrapper script instead of copying the binary
    # (copying breaks dynamic library paths on macOS)
    cat > "$INSTALL_DIR/python3" << PYEOF
#!/bin/bash
exec "$SYSTEM_PYTHON" "\$@"
PYEOF
    chmod +x "$INSTALL_DIR/python3"
    echo "   ✓ Created Python wrapper at $INSTALL_DIR/python3"
    echo "   ℹ️  Note: Grant Full Disk Access to: $SYSTEM_PYTHON"
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
launchctl bootout gui/$(id -u)/com.briefdesk.search-service 2>/dev/null || true
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

# Check if Node.js is installed (check common paths)
NODE_PATH=""
if [ -f "/usr/local/bin/node" ]; then
    NODE_PATH="/usr/local/bin/node"
elif [ -f "/opt/homebrew/bin/node" ]; then
    NODE_PATH="/opt/homebrew/bin/node"
elif [ -f "/opt/homebrew/opt/node/bin/node" ]; then
    NODE_PATH="/opt/homebrew/opt/node/bin/node"
elif command -v node &> /dev/null; then
    NODE_PATH=$(which node)
fi

if [ -z "$NODE_PATH" ]; then
    echo "   Node.js not found. Downloading Node.js LTS..."
    ARCH=$(uname -m)
    [ "$ARCH" = "arm64" ] && NODE_ARCH="arm64" || NODE_ARCH="x64"
    NODE_DL_URL="https://nodejs.org/dist/v22.13.1/node-v22.13.1-darwin-${NODE_ARCH}.tar.gz"
    NODE_TMP="/tmp/briefdesk-node-install"
    mkdir -p "$NODE_TMP"
    if curl -fsSL "$NODE_DL_URL" -o "$NODE_TMP/node.tar.gz" 2>/dev/null; then
        tar -xzf "$NODE_TMP/node.tar.gz" -C "$NODE_TMP" --strip-components=1 2>/dev/null
        [ -f "$NODE_TMP/bin/node" ] && NODE_PATH="$NODE_TMP/bin/node" && echo "   ✓ Node.js downloaded"
        rm -f "$NODE_TMP/node.tar.gz"
    else
        echo "   ⚠️  Failed to download Node.js (no internet?)"
    fi
fi

if [ -n "$NODE_PATH" ]; then
    NODE_VERSION=$("$NODE_PATH" --version)
    echo "   Found Node.js $NODE_VERSION at $NODE_PATH"
    
    # Copy Node binary for FDA
    cp "$NODE_PATH" "$DEVSAI_DIR/node"
    chmod +x "$DEVSAI_DIR/node"
    echo "   ✓ Copied Node to $DEVSAI_DIR/node"
    
    # Check if devsai is installed and set up module resolution
    # The dist files use bare imports (@modelcontextprotocol/sdk etc.)
    # so we need node_modules available for resolution
    DEVSAI_SRC=""
    DEVSAI_DIST=""
    
    # Priority 1: Development repo (has its own node_modules with all deps)
    if [ -d "$HOME/Documents/GitHub/devs-ai-cli/dist" ] && [ -d "$HOME/Documents/GitHub/devs-ai-cli/node_modules" ]; then
        DEVSAI_SRC="$HOME/Documents/GitHub/devs-ai-cli"
        DEVSAI_DIST="$DEVSAI_SRC/dist"
        echo "   Found devsai dev repo at $DEVSAI_SRC"
    fi
    
    # Priority 2: Global npm install
    if [ -z "$DEVSAI_SRC" ]; then
        NPM_ROOT=""
        # Try npm root -g with common npm paths (pkg installer may not have npm in PATH)
        for NPM_BIN in "npm" "/opt/homebrew/bin/npm" "/usr/local/bin/npm"; do
            if command -v "$NPM_BIN" &> /dev/null || [ -x "$NPM_BIN" ]; then
                NPM_ROOT=$("$NPM_BIN" root -g 2>/dev/null)
                [ -n "$NPM_ROOT" ] && break
            fi
        done
        
        if [ -n "$NPM_ROOT" ] && [ -d "$NPM_ROOT/devsai/dist" ]; then
            DEVSAI_SRC="$NPM_ROOT/devsai"
            DEVSAI_DIST="$DEVSAI_SRC/dist"
            echo "   Found devsai global install at $DEVSAI_SRC"
        fi
    fi
    
    if [ -n "$DEVSAI_DIST" ] && [ -d "$DEVSAI_DIST" ]; then
        # Copy dist files for the CLI wrapper
        cp -r "$DEVSAI_DIST" "$DEVSAI_DIR/"
        echo "   ✓ Copied devsai dist to $DEVSAI_DIR/dist"
        
        # Create package.json with type: module (ESM) and version info
        # The dist files use export/import syntax and read version from package.json
        DEVSAI_VERSION=""
        if [ -f "$DEVSAI_SRC/package.json" ]; then
            DEVSAI_VERSION=$("$NODE_PATH" -e "console.log(require('$DEVSAI_SRC/package.json').version)" 2>/dev/null)
        fi
        echo "{\"type\": \"module\", \"name\": \"devsai\", \"version\": \"${DEVSAI_VERSION:-0.0.0}\"}" > "$DEVSAI_DIR/package.json"
        
        # Set up node_modules for bare import resolution
        # The search-service loads devsai dist files which import from
        # @modelcontextprotocol/sdk etc. - these need node_modules to resolve
        rm -f "$DEVSAI_DIR/node_modules" 2>/dev/null  # Remove stale symlink
        rm -rf "$DEVSAI_DIR/node_modules" 2>/dev/null  # Remove stale dir
        
        if [ -d "$DEVSAI_SRC/node_modules" ]; then
            # Link to the source package's node_modules (dev repo or global)
            ln -sf "$DEVSAI_SRC/node_modules" "$DEVSAI_DIR/node_modules"
            echo "   ✓ Linked node_modules for dependency resolution"
        elif [ -n "$NPM_ROOT" ]; then
            # Fallback: link global npm root as node_modules
            # (global packages are siblings, so this provides resolution)
            ln -sf "$NPM_ROOT" "$DEVSAI_DIR/node_modules"
            echo "   ✓ Linked global npm root for dependency resolution"
        fi
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
    
    # ============================================
    # Setup GitHub MCP Server
    # ============================================
    echo ""
    echo "🐙 Setting up GitHub MCP Server..."
    
    GITHUB_MCP_BIN="$INSTALL_DIR/github-mcp-server"
    if [ -f "$GITHUB_MCP_BIN" ]; then
        echo "   ✓ GitHub MCP server already installed"
    else
        # Detect architecture
        ARCH=$(uname -m)
        if [ "$ARCH" = "arm64" ]; then
            GH_MCP_ASSET="github-mcp-server_Darwin_arm64.tar.gz"
        else
            GH_MCP_ASSET="github-mcp-server_Darwin_x86_64.tar.gz"
        fi
        
        echo "   Downloading GitHub MCP server ($ARCH)..."
        # Get latest release download URL
        GH_MCP_URL="https://github.com/github/github-mcp-server/releases/latest/download/$GH_MCP_ASSET"
        
        if curl -fsSL "$GH_MCP_URL" -o "/tmp/$GH_MCP_ASSET" 2>/dev/null; then
            # Extract binary from tarball
            tar -xzf "/tmp/$GH_MCP_ASSET" -C /tmp github-mcp-server 2>/dev/null
            if [ -f "/tmp/github-mcp-server" ]; then
                mv "/tmp/github-mcp-server" "$GITHUB_MCP_BIN"
                chmod +x "$GITHUB_MCP_BIN"
                echo "   ✓ GitHub MCP server installed at $GITHUB_MCP_BIN"
            else
                echo "   ⚠️  Failed to extract GitHub MCP server"
            fi
            rm -f "/tmp/$GH_MCP_ASSET"
        else
            echo "   ⚠️  Failed to download GitHub MCP server (no internet or GitHub unreachable)"
            echo "      Download manually from: https://github.com/github/github-mcp-server/releases"
        fi
    fi
    
    # ============================================
    # Setup Google Drive MCP
    # ============================================
    if [ -d "$INSTALL_DIR/gdrive-mcp" ]; then
        echo ""
        echo "📁 Setting up Google Drive MCP..."
        cd "$INSTALL_DIR/gdrive-mcp"
        npm install --silent 2>/dev/null
        npm run build --silent 2>/dev/null
        echo "   ✓ Google Drive MCP ready"
        echo "   To authenticate: cd ~/.local/share/briefdesk/gdrive-mcp && npm run auth"
        cd "$INSTALL_DIR"
    fi
    
    # ============================================
    # Setup Gmail MCP
    # ============================================
    if [ -d "$INSTALL_DIR/gmail-mcp" ]; then
        echo ""
        echo "📧 Setting up Gmail MCP..."
        cd "$INSTALL_DIR/gmail-mcp"
        npm install --silent 2>/dev/null
        npm run build --silent 2>/dev/null
        if [ -f "$INSTALL_DIR/gmail-mcp/dist/index.js" ]; then
            echo "   ✓ Gmail MCP ready"
        else
            echo "   ⚠️  Gmail MCP build failed (will retry on next restart)"
        fi
        cd "$INSTALL_DIR"
    fi
    
    # ============================================
    # Patch Gmail MCP for Read-Only (Security)
    # ============================================
    echo ""
    echo "🔒 Patching Gmail MCP for read-only access..."
    
    # Find and patch Gmail MCP installations to use readonly scope
    GMAIL_MCP_PATHS=(
        "/opt/homebrew/lib/node_modules/@monsoft/mcp-gmail/dist/utils/gmail.js"
        "/usr/local/lib/node_modules/@monsoft/mcp-gmail/dist/utils/gmail.js"
    )
    PATCHED=false
    for gmail_path in "${GMAIL_MCP_PATHS[@]}"; do
        if [ -f "$gmail_path" ]; then
            sed -i '' 's/gmail\.modify/gmail.readonly/g' "$gmail_path" 2>/dev/null && PATCHED=true
        fi
    done
    
    # Also patch via npx cache (bash 3.2 compatible)
    if [ -d ~/.npm/_npx ]; then
        while IFS= read -r f; do
            if [ -f "$f" ]; then
                sed -i '' 's/gmail\.modify/gmail.readonly/g' "$f" 2>/dev/null && PATCHED=true
            fi
        done < <(find ~/.npm/_npx -type f -path "*/node_modules/@monsoft/mcp-gmail/dist/utils/gmail.js" 2>/dev/null)
    fi
    
    if [ "$PATCHED" = true ]; then
        echo "   ✓ Gmail MCP patched for read-only access"
        # Remove credentials with modify scope
        if [ -f ~/.gmail-mcp/credentials.json ]; then
            if grep -q "gmail.modify" ~/.gmail-mcp/credentials.json 2>/dev/null; then
                rm -f ~/.gmail-mcp/credentials.json
                echo "   ⚠️  Removed old Gmail credentials - re-authenticate with: npx @monsoft/mcp-gmail auth"
            fi
        fi
    else
        echo "   ℹ️  Gmail MCP not found (install later with: npm install -g @monsoft/mcp-gmail)"
    fi
    
    # ============================================
    # Setup Node.js Search Service
    # ============================================
    echo ""
    echo "🔎 Setting up AI Search Service..."
    
    if [ -f "$INSTALL_DIR/search-service.mjs" ]; then
        # Create search service LaunchAgent
        cat > "$LAUNCHAGENTS_DIR/com.briefdesk.search-service.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.briefdesk.search-service</string>
    <key>ProgramArguments</key>
    <array>
        <string>$DEVSAI_DIR/node</string>
        <string>$INSTALL_DIR/search-service.mjs</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>$HOME</string>
        <key>SEARCH_SERVICE_PORT</key>
        <string>19765</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/briefdesk-search-service.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/briefdesk-search-service.log</string>
</dict>
</plist>
EOF
        echo "   ✓ Created search service LaunchAgent"
        
        # Start the search service
        launchctl bootstrap gui/$(id -u) "$LAUNCHAGENTS_DIR/com.briefdesk.search-service.plist" 2>/dev/null || true
        echo "   ✓ Started AI Search Service on port 19765"
    else
        echo "   ℹ️  search-service.mjs not found, skipping"
    fi
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
# Save system metadata for installer.html
PYTHON_REAL=$("$SYSTEM_PYTHON" -c "import os, sys; print(os.path.realpath(sys.executable))" 2>/dev/null || echo "$SYSTEM_PYTHON")
PYTHON_VER=$("$SYSTEM_PYTHON" --version 2>&1 || echo "unknown")
NODE_VER=$("$DEVSAI_DIR/node" --version 2>/dev/null || echo "")
cat > "$INSTALL_DIR/.install-meta.json" << METAEOF
{
  "python_path": "$SYSTEM_PYTHON",
  "python_real_path": "$PYTHON_REAL",
  "python_version": "$PYTHON_VER",
  "node_path": "${NODE_PATH:-}",
  "node_version": "$NODE_VER",
  "node_source": "system",
  "node_fda_path": "$DEVSAI_DIR/node",
  "install_dir": "$INSTALL_DIR",
  "devsai_dir": "$DEVSAI_DIR",
  "github_mcp": "$([ -f "$INSTALL_DIR/github-mcp-server" ] && echo 'installed' || echo 'missing')",
  "devsai_cli": "$([ -f "$DEVSAI_DIR/devsai.sh" ] && echo 'installed' || echo 'missing')",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
METAEOF

echo "🔗 Opening BriefDesk Installer..."
echo ""

# Wait for servers to be ready
echo "⏳ Waiting for servers to start..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:18765/debug > /dev/null 2>&1; then
        echo "✅ Servers are ready!"
        sleep 1
        open "http://127.0.0.1:8765/installer.html"
        exit 0
    fi
    sleep 1
done

echo "⚠️  Servers may still be starting. Opening installer page anyway..."
open "http://127.0.0.1:8765/installer.html"
