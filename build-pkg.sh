#!/bin/bash
# Build BriefDesk .pkg installer
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/pkg-build"
PKG_ROOT="$BUILD_DIR/root"
PKG_SCRIPTS="$SCRIPT_DIR/pkg-installer/scripts"
# Get version from git tag (if available) or default
if [[ -n "${GITHUB_REF_NAME:-}" && "${GITHUB_REF_NAME}" == v* ]]; then
    VERSION="${GITHUB_REF_NAME#v}"
elif git describe --tags --exact-match 2>/dev/null | grep -q '^v'; then
    VERSION="$(git describe --tags --exact-match | sed 's/^v//')"
else
    VERSION="1.0.0"
fi
IDENTIFIER="com.briefdesk.app"
OUTPUT_PKG="$SCRIPT_DIR/BriefDesk-$VERSION.pkg"

# Check for unsigned flag
UNSIGNED=false
if [[ "$1" == "--unsigned" ]]; then
    UNSIGNED=true
    echo "⚠️  Building UNSIGNED package (for testing only)"
fi

# Code signing & notarization config
DEVELOPER_ID="Developer ID Installer: Elias Khalifeh (9XR2RP3P8V)"
TEAM_ID="9XR2RP3P8V"

echo "🏗️  Building BriefDesk.pkg..."

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$PKG_ROOT/usr/local/share/briefdesk"

# Copy application files
echo "📦 Copying application files..."
cp "$SCRIPT_DIR/search-server.py" "$PKG_ROOT/usr/local/share/briefdesk/"
cp "$SCRIPT_DIR/search-service.mjs" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true
cp "$SCRIPT_DIR/start.html" "$PKG_ROOT/usr/local/share/briefdesk/"
cp "$SCRIPT_DIR/installer.html" "$PKG_ROOT/usr/local/share/briefdesk/"
cp "$SCRIPT_DIR/devsai.example.json" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true
cp "$SCRIPT_DIR/config.example.json" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true

# Copy directories
cp -r "$SCRIPT_DIR/css" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/js" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/lib" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/assets" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/icons" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/browser-extension" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true
# Copy gdrive-mcp excluding node_modules and dist (built during postinstall)
if [ -d "$SCRIPT_DIR/gdrive-mcp" ]; then
    mkdir -p "$PKG_ROOT/usr/local/share/briefdesk/gdrive-mcp"
    rsync -a --exclude='node_modules' --exclude='dist' "$SCRIPT_DIR/gdrive-mcp/" "$PKG_ROOT/usr/local/share/briefdesk/gdrive-mcp/" 2>/dev/null || \
        cp -r "$SCRIPT_DIR/gdrive-mcp" "$PKG_ROOT/usr/local/share/briefdesk/"
fi

# Copy gmail-mcp excluding node_modules and dist (built during postinstall)
if [ -d "$SCRIPT_DIR/gmail-mcp" ]; then
    mkdir -p "$PKG_ROOT/usr/local/share/briefdesk/gmail-mcp"
    rsync -a --exclude='node_modules' --exclude='dist' "$SCRIPT_DIR/gmail-mcp/" "$PKG_ROOT/usr/local/share/briefdesk/gmail-mcp/" 2>/dev/null || \
        cp -r "$SCRIPT_DIR/gmail-mcp" "$PKG_ROOT/usr/local/share/briefdesk/"
fi

# Bundle devsai tarball (from repo-local folder for CI)
DEVSAI_TARBALL_SOURCE=$(ls -t "$SCRIPT_DIR/devsai"/devsai-*.tgz 2>/dev/null | head -1)
if [ -n "$DEVSAI_TARBALL_SOURCE" ]; then
    mkdir -p "$PKG_ROOT/usr/local/share/briefdesk/devsai"
    cp "$DEVSAI_TARBALL_SOURCE" "$PKG_ROOT/usr/local/share/briefdesk/devsai/devsai.tgz"
    echo "📦 Bundled devsai tarball: $(basename "$DEVSAI_TARBALL_SOURCE")"
else
    echo "⚠️  No devsai tarball found in ./devsai (devsai-*.tgz)"
fi

# Embed Google OAuth credentials if provided
if [[ -n "${GOOGLE_CLIENT_ID:-}" && -n "${GOOGLE_CLIENT_SECRET:-}" ]]; then
    echo "🔑 Embedding Google OAuth credentials..."
    CONFIG_FILE="$PKG_ROOT/usr/local/share/briefdesk/lib/config.py"
    # Replace the empty defaults with actual values
    sed -i '' "s|GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')|GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '${GOOGLE_CLIENT_ID}')|" "$CONFIG_FILE"
    sed -i '' "s|GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')|GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '${GOOGLE_CLIENT_SECRET}')|" "$CONFIG_FILE"
else
    echo "⚠️  No GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET set - OAuth connect button will be disabled"
fi

# Embed Slack OAuth credentials if provided
if [[ -n "${SLACK_CLIENT_ID:-}" && -n "${SLACK_CLIENT_SECRET:-}" ]]; then
    echo "🔑 Embedding Slack OAuth credentials..."
    SERVER_FILE="$PKG_ROOT/usr/local/share/briefdesk/search-server.py"
    sed -i '' "s|SLACK_OAUTH_CLIENT_ID = os.environ.get('SLACK_CLIENT_ID', '')|SLACK_OAUTH_CLIENT_ID = os.environ.get('SLACK_CLIENT_ID', '${SLACK_CLIENT_ID}')|" "$SERVER_FILE"
    sed -i '' "s|SLACK_OAUTH_CLIENT_SECRET = os.environ.get('SLACK_CLIENT_SECRET', '')|SLACK_OAUTH_CLIENT_SECRET = os.environ.get('SLACK_CLIENT_SECRET', '${SLACK_CLIENT_SECRET}')|" "$SERVER_FILE"
else
    echo "⚠️  No SLACK_CLIENT_ID/SLACK_CLIENT_SECRET set - Slack OAuth button will show as not configured"
fi

# Make postinstall executable
chmod +x "$PKG_SCRIPTS/postinstall"

echo "🔨 Building component package..."
pkgbuild \
    --root "$PKG_ROOT" \
    --scripts "$PKG_SCRIPTS" \
    --identifier "$IDENTIFIER" \
    --version "$VERSION" \
    --install-location "/" \
    "$BUILD_DIR/BriefDesk-component.pkg"

echo "📋 Creating distribution..."
cat > "$BUILD_DIR/distribution.xml" << EOF
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>BriefDesk</title>
    <organization>com.briefdesk</organization>
    <domains enable_localSystem="true"/>
    <options customize="never" require-scripts="true" rootVolumeOnly="true" hostArchitectures="arm64,x86_64"/>
    
    <welcome file="welcome.html"/>
    <conclusion file="conclusion.html"/>
    
    <choices-outline>
        <line choice="default">
            <line choice="com.briefdesk.app"/>
        </line>
    </choices-outline>
    
    <choice id="default"/>
    <choice id="com.briefdesk.app" visible="false">
        <pkg-ref id="com.briefdesk.app"/>
    </choice>
    
    <pkg-ref id="com.briefdesk.app" version="$VERSION" onConclusion="none">BriefDesk-component.pkg</pkg-ref>
</installer-gui-script>
EOF

# Create welcome HTML
cat > "$BUILD_DIR/welcome.html" << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 20px; background: #1a1a2e; color: #e0e0e0; }
        h1 { color: #4f8cff; margin-bottom: 10px; }
        p { line-height: 1.6; }
        .feature { margin: 8px 0; padding-left: 20px; }
        .feature:before { content: "✓"; color: #34d399; margin-left: -20px; margin-right: 8px; }
    </style>
</head>
<body>
    <h1>Welcome to BriefDesk</h1>
    <p>Your productivity dashboard that brings everything together.</p>
    
    <h3 style="margin-top: 20px; color: #a0a0a0;">Features:</h3>
    <div class="feature">Unified search across Safari history, files, and apps</div>
    <div class="feature">AI-powered semantic search with Claude, GPT, and Gemini</div>
    <div class="feature">Calendar integration with meeting prep</div>
    <div class="feature">Slack, Gmail, Jira, and Confluence integration</div>
    <div class="feature">Google Drive full-text search</div>
    
    <p style="margin-top: 20px; font-size: 13px; color: #a0a0a0;">
        Installation takes about 2 minutes.
    </p>
</body>
</html>
EOF

# Create conclusion HTML
cat > "$BUILD_DIR/conclusion.html" << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 20px; background: #1a1a2e; color: #e0e0e0; }
        h1 { color: #34d399; margin-bottom: 8px; font-size: 22px; }
        p { line-height: 1.6; margin: 8px 0; }
        .subtitle { color: #a0a0a0; font-size: 14px; margin-bottom: 16px; }
        a { color: #4f8cff; }
        .check { color: #34d399; margin-right: 6px; }
        .done-list { margin: 16px 0; font-size: 13px; color: #c0c0c0; list-style: none; padding: 0; }
        .done-list li { margin: 6px 0; }
        .next { margin-top: 20px; padding: 14px 16px; background: rgba(79,140,255,0.1); border: 1px solid rgba(79,140,255,0.3); border-radius: 8px; }
        .next strong { color: #4f8cff; }
    </style>
</head>
<body>
    <h1>Installation Complete</h1>
    <p class="subtitle">BriefDesk is installed and running. Python, Node.js, and all services were set up automatically.</p>
    
    <ul class="done-list">
        <li><span class="check">&#10003;</span> Python detected and configured</li>
        <li><span class="check">&#10003;</span> Node.js ready (downloaded automatically if needed)</li>
        <li><span class="check">&#10003;</span> Background services started</li>
        <li><span class="check">&#10003;</span> AI search engine installed</li>
    </ul>
    
    <div class="next">
        <strong>Next:</strong> Open the setup wizard to connect your accounts.<br><br>
        <a href="http://127.0.0.1:8765/installer.html" target="_blank" style="font-weight: 600; font-size: 15px;">Open Setup Wizard &rarr;</a>
    </div>
</body>
</html>
EOF

if [[ "$UNSIGNED" == "true" ]]; then
    echo "📦 Building unsigned installer..."
    productbuild \
        --distribution "$BUILD_DIR/distribution.xml" \
        --resources "$BUILD_DIR" \
        --package-path "$BUILD_DIR" \
        "$OUTPUT_PKG"
    rm -rf "$BUILD_DIR"
    echo ""
    echo "✅ Unsigned package built: $OUTPUT_PKG"
else
    # Require credentials for signed builds
    : "${APPLE_ID:?Set APPLE_ID environment variable}"
    : "${APP_PASSWORD:?Set APP_PASSWORD environment variable}"

    echo "📦 Building and signing installer..."
    productbuild \
        --distribution "$BUILD_DIR/distribution.xml" \
        --resources "$BUILD_DIR" \
        --package-path "$BUILD_DIR" \
        --sign "$DEVELOPER_ID" \
        "$OUTPUT_PKG"

    rm -rf "$BUILD_DIR"

    echo "🔐 Notarizing package with Apple..."
    xcrun notarytool submit "$OUTPUT_PKG" \
        --apple-id "$APPLE_ID" \
        --password "$APP_PASSWORD" \
        --team-id "$TEAM_ID" \
        --wait

    echo "📎 Stapling notarization ticket..."
    xcrun stapler staple "$OUTPUT_PKG"

    echo ""
    echo "✅ Package signed and notarized: $OUTPUT_PKG"
fi
