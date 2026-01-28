# Safari Start Page

A beautiful, fast, customizable start page for Safari with real-time history search.

![Screenshot](screenshot.png)

## Features

- **Instant loading** - Static HTML served locally (~3ms load time)
- **Real-time history search** - Search Safari and Dia browser history as you type
- **Smart search** - Multi-word queries, visit count ranking, URL detection
- **WAL support** - Reads Safari's write-ahead log for truly real-time results
- **Customizable** - Edit name, quick links, background, and theme via settings gear
- **URL detection** - Type a URL and press Enter to navigate directly
- **Keyboard navigation** - Full keyboard support for search results
- **Dark/Light themes** - Choose UI style to match your background
- **Custom backgrounds** - Gradient presets, custom gradients, or upload an image
- **No external requests** - 100% local, privacy-focused

## Requirements

- macOS (tested on Sonoma/Sequoia)
- Safari
- Python 3 (included with Xcode Command Line Tools)

## Installation

### Quick Install

```bash
chmod +x install.sh
./install.sh
```

### Manual Install

1. **Copy files:**
   ```bash
   mkdir -p ~/.local/share/safari_start_page
   cp start.html search-server.py ~/.local/share/safari_start_page/
   ```

2. **Install LaunchAgents:**
   ```bash
   cp launchagents/*.plist ~/Library/LaunchAgents/
   # Edit plists to replace HOME_DIR with your home directory path
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.startpage.static.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.startpage.search.plist
   ```

3. **Grant Full Disk Access** (required for Safari history):
   - System Settings → Privacy & Security → Full Disk Access
   - Add: `/Applications/Xcode.app/Contents/Developer/usr/bin/python3`
   - (Or the Python that `/usr/bin/python3 -c "import sys; print(sys.executable)"` shows)

4. **Set Safari homepage:**
   - Safari → Settings → General
   - Homepage: `http://127.0.0.1:8765/start.html`
   - New windows/tabs open with: Homepage

## Customization

Click the **gear icon** (⚙️) in the bottom-right corner to open settings where you can:
- Set your name (for personalized greetings)
- Add, edit, or remove quick links (with custom icons)
- Choose a background (gradient presets, custom gradient, or upload image)
- Switch between Dark UI and Light UI themes

Settings are stored in localStorage and persist across sessions.

## How It Works

Two lightweight servers run in the background:

1. **Static server** (port 8765) - Serves HTML/CSS
2. **Search server** (port 18765) - Queries Safari's history database

The search server:
- Copies Safari's History.db + WAL files to a temp location
- Runs a WAL checkpoint to include recent browsing
- Searches with smart ranking (visit count, title match, domain match)
- Cleans up temp files after each query

## Search Features

- **Single word**: `github` → matches URLs and titles containing "github"
- **Multi-word**: `figma design` → matches entries containing both words
- **URL navigation**: `github.com` → navigates directly to the URL
- **Visit count**: Results ranked by how often you visit them
- **Real-time**: Reads Safari's WAL file for immediate results

## Troubleshooting

### Search not finding recent pages
Safari buffers history writes. The search server reads the WAL file for real-time results, but if issues persist:
1. Quit Safari completely (Cmd+Q)
2. Reopen Safari
3. Search again

### Permission denied
Ensure Full Disk Access is granted to the Python binary that launchd uses:
```bash
/usr/bin/python3 -c "import sys; print(sys.executable)"
```
Add that path to Full Disk Access in System Settings.

### Check server status
```bash
curl http://127.0.0.1:18765/debug
curl http://127.0.0.1:8765/start.html
```

### Restart servers
```bash
launchctl kickstart -k gui/$(id -u)/com.startpage.static
launchctl kickstart -k gui/$(id -u)/com.startpage.search
```

### Uninstall
```bash
launchctl bootout gui/$(id -u)/com.startpage.static
launchctl bootout gui/$(id -u)/com.startpage.search
rm ~/Library/LaunchAgents/com.startpage.*.plist
rm -rf ~/.local/share/safari_start_page
```

## Files

```
safari_start_page/
├── start.html           # Main start page (customizable)
├── search-server.py     # History search server
├── install.sh           # Installation script
├── launchagents/
│   ├── com.startpage.static.plist
│   └── com.startpage.search.plist
└── README.md
```

## Privacy

- **100% local** - No external API calls or tracking
- **No data collection** - History stays on your machine
- **Localhost only** - Servers bind to 127.0.0.1

## License

MIT License - feel free to customize and share!

## Contributing

Pull requests welcome! Ideas for improvements:
- [ ] Chrome/Firefox history support
- [ ] Bookmark folder organization
- [ ] Keyboard shortcuts for quick links
- [ ] Weather widget
