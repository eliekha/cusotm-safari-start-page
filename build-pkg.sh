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
cp -r "$SCRIPT_DIR/gdrive-mcp" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true

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
    
    <p style="margin-top: 20px; font-size: 12px; color: #808080;">
        Requires: Python 3, Node.js (optional for AI features)
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
        .features { margin: 16px 0; font-size: 13px; color: #a0a0a0; }
        .features li { margin: 4px 0; }
        .tip { margin-top: 16px; padding: 10px 12px; background: rgba(255,255,255,0.05); border-radius: 6px; font-size: 12px; color: #808080; }
        .tip code { background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 4px; font-family: 'SF Mono', Monaco, monospace; }
    </style>
</head>
<body>
    <h1>Installation Complete</h1>
    <p class="subtitle">BriefDesk is installed and running in the background.</p>
    
    <p><strong>One more step:</strong> Open the setup wizard to configure permissions and connect your accounts.</p>
    
    <p style="margin: 16px 0;">
        <a href="http://localhost:8765/installer.html" target="_blank" style="font-weight: 600; font-size: 14px;">Open Setup Wizard</a>
    </p>
    
    <div class="features">
        <strong>The wizard will help you:</strong>
        <ul>
            <li>Grant Full Disk Access for Safari history search</li>
            <li>Connect Slack, Gmail, Calendar, and Drive</li>
            <li>Enable AI-powered semantic search</li>
        </ul>
    </div>
    
    <div class="tip">
        <strong>Tip:</strong> After setup, set your browser homepage to <code>http://localhost:8765/start.html</code>
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
