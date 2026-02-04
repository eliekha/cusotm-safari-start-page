---
name: packaging
description: Build macOS .pkg installer for BriefDesk distribution. Use when the user wants to create a package, build an installer, distribute BriefDesk, or mentions .pkg files.
---

# BriefDesk Packaging

Build and distribute BriefDesk as a macOS `.pkg` installer.

## Quick Build

```bash
cd /Users/elias.khalifeh/Documents/briefdesk
./build-pkg.sh
```

Output: `BriefDesk-1.0.0.pkg`

## Architecture

### Build Script: `build-pkg.sh`

The script performs these steps:

1. **Clean & Create Structure**
   - Removes previous `pkg-build/` directory
   - Creates `pkg-build/root/usr/local/share/briefdesk/`

2. **Copy Application Files**
   - Python server: `search-server.py`
   - Node.js service: `search-service.mjs`
   - HTML pages: `start.html`, `installer.html`
   - Config examples: `devsai.example.json`, `config.example.json`

3. **Copy Directories**
   - `css/` - Stylesheets
   - `js/` - Frontend JavaScript
   - `lib/` - Python modules
   - `assets/` - Logo images
   - `icons/` - Browser icons (Chrome, Firefox, Safari)
   - `gdrive-mcp/` - Google Drive MCP server
   - `devsai-*.tgz` - Bundled DevsAI CLI tarball (from `./devsai/`)

4. **Build Component Package**
   ```bash
   pkgbuild --root pkg-build/root \
            --scripts pkg-installer/scripts \
            --identifier com.briefdesk.app \
            --version 1.0.0 \
            --install-location "/" \
            pkg-build/BriefDesk-component.pkg
   ```

5. **Create Distribution**
   - Generates `distribution.xml` for installer UI
   - Creates `welcome.html` and `conclusion.html`

6. **Build Final Installer**
   ```bash
   productbuild --distribution pkg-build/distribution.xml \
                --resources pkg-build \
                --package-path pkg-build \
                BriefDesk-1.0.0.pkg
   ```

### Postinstall Script: `pkg-installer/scripts/postinstall`

Runs after file installation to set up user environment:

1. **Detect Install User** - Gets the user who initiated install
2. **Copy to User Directory** - Copies from `/usr/local/share/briefdesk/` to `~/.local/share/briefdesk/`
3. **Create Python Wrapper** - Creates wrapper script that calls system Python (avoids dynamic library issues)
4. **Copy Node.js** - Copies Node binary to `~/.local/share/devsai/node`
5. **Create LaunchAgents** - Sets up three services:
   - `com.briefdesk.static` (port 8765) - Static file server
   - `com.briefdesk.server` (port 18765) - Main API server
   - `com.briefdesk.search-service` (port 18766) - Node.js MCP service
6. **Install DevsAI CLI (if bundled)** - Installs from `devsai.tgz` into `~/.local/share/devsai`
7. **Build gdrive-mcp** - Runs `npm install && npm run build` if present
8. **Start Services** - Bootstraps all LaunchAgents

## Key Design Decisions

### Python Wrapper Script

Instead of copying the Python binary (which breaks on macOS due to dynamic library linking), we create a wrapper script:

```bash
#!/bin/bash
exec "/opt/homebrew/bin/python3" "$@"
```

This ensures:
- No `library not loaded` errors
- FDA is granted to the actual Python binary, not a copy
- Works with Homebrew, system Python, or pyenv

### Node.js Path Detection

The postinstall script checks multiple locations:
1. `/opt/homebrew/bin/node` (Apple Silicon Homebrew)
2. `/usr/local/bin/node` (Intel Homebrew)
3. `/opt/homebrew/opt/node/bin/node` (Homebrew versioned)
4. `which node` (fallback)

### Installation Domain

Uses `enable_localSystem="true"` in distribution.xml to install to `/usr/local/share/briefdesk/`. The postinstall then copies to user directories with proper ownership.

## Installer UI

### Welcome Screen (`welcome.html`)
- Lists features
- Shows requirements (Python 3, Node.js optional)

### Conclusion Screen (`conclusion.html`)
- Shows completion message
- Provides link to Setup Wizard (`http://127.0.0.1:8765/installer.html`)
- Lists what the wizard helps configure

## Adding New Files

To include new files in the package:

1. **Single Files** - Add to the copy section:
   ```bash
   cp "$SCRIPT_DIR/newfile.py" "$PKG_ROOT/usr/local/share/briefdesk/"
   ```

2. **Directories** - Add to the directory copy section:
   ```bash
   cp -r "$SCRIPT_DIR/newfolder" "$PKG_ROOT/usr/local/share/briefdesk/" 2>/dev/null || true
   ```

3. **Rebuild** - Run `./build-pkg.sh`

## Bundling DevsAI

To bundle DevsAI in the package:

1. Place a tarball in `./devsai/` (e.g., `devsai-latest.tgz`)
2. Build the package — the newest `devsai-*.tgz` is copied to:
   `/usr/local/share/briefdesk/devsai/devsai.tgz`
3. Postinstall installs it to `~/.local/share/devsai/` and creates:
   - `~/.local/share/devsai/devsai.sh`
   - `~/.local/bin/devsai` (symlink)

## Testing

### Test Installation
```bash
# Install the package
sudo installer -pkg BriefDesk-1.0.0.pkg -target /

# Check files were installed
ls -la /usr/local/share/briefdesk/

# Check user files were created
ls -la ~/.local/share/briefdesk/

# Check services are running
lsof -i:8765
lsof -i:18765
```

### Test Uninstall
```bash
# Stop services
launchctl bootout gui/$(id -u)/com.briefdesk.static
launchctl bootout gui/$(id -u)/com.briefdesk.server
launchctl bootout gui/$(id -u)/com.briefdesk.search-service

# Remove files
rm ~/Library/LaunchAgents/com.briefdesk.*.plist
rm -rf ~/.local/share/briefdesk
sudo rm -rf /usr/local/share/briefdesk
```

## Versioning

To update the version:

1. Edit `build-pkg.sh`:
   ```bash
   VERSION="1.1.0"  # Change this
   ```

2. Rebuild: `./build-pkg.sh`

Output filename will be `BriefDesk-1.1.0.pkg`

## Troubleshooting

### Package fails to build
- Ensure `pkg-installer/scripts/postinstall` is executable: `chmod +x pkg-installer/scripts/postinstall`
- Check for syntax errors in the script

### Services don't start after install
- Check LaunchAgent logs: `cat /tmp/briefdesk-*.log`
- Verify Python/Node paths in the created LaunchAgents
- Run postinstall manually: `sudo /usr/local/share/briefdesk/pkg-installer/scripts/postinstall`

### Icons not loading in installer.html
- Ensure `icons/` folder is in the copy list in `build-pkg.sh`
- Rebuild the package
