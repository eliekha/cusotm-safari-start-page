#!/bin/bash
# Build BriefDesk .pkg installer
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/pkg-build"
PKG_ROOT="$BUILD_DIR/root"
PKG_SCRIPTS="$SCRIPT_DIR/pkg-installer/scripts"
VERSION="1.0.0"
IDENTIFIER="com.briefdesk.app"
OUTPUT_PKG="$SCRIPT_DIR/BriefDesk-$VERSION.pkg"

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
cp -r "$SCRIPT_DIR/gdrive-mcp" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true

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
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 20px; background: #1a1a2e; color: #e0e0e0; }
        h1 { color: #34d399; margin-bottom: 8px; }
        p { line-height: 1.6; margin: 8px 0; }
        .subtitle { color: #a0a0a0; font-size: 14px; }
        .next-box { margin: 20px 0; padding: 16px; background: rgba(79,140,255,0.1); border: 1px solid rgba(79,140,255,0.3); border-radius: 12px; }
        .next-title { color: #4f8cff; font-weight: 600; margin-bottom: 8px; }
        .url-box { margin: 12px 0; padding: 12px 16px; background: rgba(0,0,0,0.3); border-radius: 8px; font-family: 'SF Mono', Monaco, monospace; font-size: 13px; color: #34d399; word-break: break-all; }
        .instructions { margin-top: 16px; font-size: 13px; color: #a0a0a0; }
        .instructions li { margin: 6px 0; }
    </style>
</head>
<body>
    <h1>✓ Installation Complete!</h1>
    <p class="subtitle">BriefDesk has been installed and services are starting.</p>
    
    <div class="next-box">
        <div class="next-title">Next: Complete Setup</div>
        <p>Click <strong>Close</strong> below, then open this URL in your browser:</p>
        <div class="url-box">http://127.0.0.1:8765/installer.html</div>
    </div>
    
    <div class="instructions">
        <strong>The setup wizard will help you:</strong>
        <ul>
            <li>Grant Full Disk Access permissions</li>
            <li>Connect Slack, Gmail, and Calendar</li>
            <li>Set up AI-powered search</li>
        </ul>
    </div>
    
    <p style="margin-top: 16px; font-size: 12px; color: #606060;">
        Tip: Set your browser homepage to <code style="background:rgba(255,255,255,0.1);padding:2px 6px;border-radius:4px;">http://127.0.0.1:8765/start.html</code>
    </p>
</body>
</html>
EOF

echo "📦 Building final installer..."
productbuild \
    --distribution "$BUILD_DIR/distribution.xml" \
    --resources "$BUILD_DIR" \
    --package-path "$BUILD_DIR" \
    "$OUTPUT_PKG"

# Clean up
rm -rf "$BUILD_DIR"

echo ""
echo "✅ Package built successfully: $OUTPUT_PKG"
echo ""
echo "To install: double-click the .pkg file or run:"
echo "  sudo installer -pkg $OUTPUT_PKG -target /"
