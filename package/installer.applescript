-- BriefDesk Installer
-- A native macOS GUI installer

use AppleScript version "2.4"
use scripting additions
use framework "Foundation"

-- Get the path to this app's Resources folder
set myPath to path to me
tell application "Finder"
	set resourcesPath to (container of myPath as text) & "Contents:Resources:"
end tell
set resourcesPosix to POSIX path of resourcesPath

-- Configuration
set appName to "BriefDesk"
set installDir to (POSIX path of (path to home folder)) & ".local/share/briefdesk"
set launchAgentsDir to (POSIX path of (path to home folder)) & "Library/LaunchAgents"

-- Welcome dialog
set welcomeResult to display dialog "Welcome to BriefDesk Installer

This will install BriefDesk, your personal productivity dashboard.

What will be installed:
• BriefDesk web app
• Background services (calendar, search)
• LaunchAgents for auto-start

Installation location:
~/.local/share/briefdesk" buttons {"Cancel", "Install"} default button "Install" with title "BriefDesk Installer" with icon note

if button returned of welcomeResult is "Cancel" then
	return
end if

-- Check dependencies
set missingDeps to {}

-- Check Python
try
	do shell script "python3 --version"
on error
	set end of missingDeps to "Python 3"
end try

-- Check Node.js
try
	do shell script "node --version"
on error
	set end of missingDeps to "Node.js"
end try

if (count of missingDeps) > 0 then
	set depList to ""
	repeat with dep in missingDeps
		set depList to depList & "• " & dep & "
"
	end repeat
	
	display dialog "Missing dependencies:

" & depList & "
Please install these first:
• Python: brew install python3
• Node.js: brew install node

Or download from:
• python.org
• nodejs.org" buttons {"OK"} default button "OK" with title "Missing Dependencies" with icon stop
	return
end if

-- Show progress
set progressText to "Installing BriefDesk..."
display notification progressText with title "BriefDesk Installer"

-- Create directories
try
	do shell script "mkdir -p '" & installDir & "'"
	do shell script "mkdir -p '" & launchAgentsDir & "'"
	do shell script "mkdir -p '" & installDir & "/css'"
	do shell script "mkdir -p '" & installDir & "/js'"
	do shell script "mkdir -p '" & installDir & "/lib'"
on error errMsg
	display dialog "Failed to create directories: " & errMsg buttons {"OK"} with icon stop
	return
end try

-- Copy files
try
	-- Main files
	do shell script "cp '" & resourcesPosix & "start.html' '" & installDir & "/'"
	do shell script "cp '" & resourcesPosix & "setup.html' '" & installDir & "/'"
	do shell script "cp '" & resourcesPosix & "search-server.py' '" & installDir & "/'"
	do shell script "cp '" & resourcesPosix & "search-service.mjs' '" & installDir & "/'"
	
	-- Directories
	do shell script "cp -r '" & resourcesPosix & "css/' '" & installDir & "/css/'"
	do shell script "cp -r '" & resourcesPosix & "js/' '" & installDir & "/js/'"
	do shell script "cp -r '" & resourcesPosix & "lib/' '" & installDir & "/lib/'"
	
	-- Config examples (don't overwrite existing)
	try
		do shell script "[ ! -f '" & installDir & "/config.json' ] && cp '" & resourcesPosix & "config.example.json' '" & installDir & "/config.json' || true"
	end try
	try
		do shell script "[ ! -f '" & installDir & "/.devsai.json' ] && cp '" & resourcesPosix & "devsai.example.json' '" & installDir & "/.devsai.json' || true"
	end try
	
on error errMsg
	display dialog "Failed to copy files: " & errMsg buttons {"OK"} with icon stop
	return
end try

-- Install LaunchAgents
set userId to do shell script "id -u"
set homeDir to POSIX path of (path to home folder)

-- Static server plist
set staticPlist to "<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
    <key>Label</key>
    <string>com.briefdesk.static</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>http.server</string>
        <string>8765</string>
    </array>
    <key>WorkingDirectory</key>
    <string>" & installDir & "</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/briefdesk-static.log</string>
    <key>StandardOutPath</key>
    <string>/tmp/briefdesk-static.log</string>
</dict>
</plist>"

-- Search server plist
set serverPlist to "<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
    <key>Label</key>
    <string>com.briefdesk.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>" & installDir & "/search-server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>" & installDir & "</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/briefdesk-server.log</string>
    <key>StandardOutPath</key>
    <string>/tmp/briefdesk-server.log</string>
</dict>
</plist>"

-- Search service plist
set servicePlist to "<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
    <key>Label</key>
    <string>com.briefdesk.search-service</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/node</string>
        <string>" & installDir & "/search-service.mjs</string>
    </array>
    <key>WorkingDirectory</key>
    <string>" & installDir & "</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/briefdesk-search-service.log</string>
    <key>StandardOutPath</key>
    <string>/tmp/briefdesk-search-service.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>" & homeDir & "</string>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>"

-- Write plist files
try
	do shell script "echo " & quoted form of staticPlist & " > '" & launchAgentsDir & "/com.briefdesk.static.plist'"
	do shell script "echo " & quoted form of serverPlist & " > '" & launchAgentsDir & "/com.briefdesk.server.plist'"
	do shell script "echo " & quoted form of servicePlist & " > '" & launchAgentsDir & "/com.briefdesk.search-service.plist'"
on error errMsg
	display dialog "Failed to create LaunchAgents: " & errMsg buttons {"OK"} with icon stop
	return
end try

-- Unload existing (ignore errors)
try
	do shell script "launchctl unload '" & launchAgentsDir & "/com.briefdesk.static.plist' 2>/dev/null || true"
	do shell script "launchctl unload '" & launchAgentsDir & "/com.briefdesk.server.plist' 2>/dev/null || true"
	do shell script "launchctl unload '" & launchAgentsDir & "/com.briefdesk.search-service.plist' 2>/dev/null || true"
end try

-- Load LaunchAgents
try
	do shell script "launchctl load '" & launchAgentsDir & "/com.briefdesk.static.plist'"
	do shell script "launchctl load '" & launchAgentsDir & "/com.briefdesk.server.plist'"
	do shell script "launchctl load '" & launchAgentsDir & "/com.briefdesk.search-service.plist'"
on error errMsg
	display dialog "Failed to start services: " & errMsg buttons {"OK"} with icon stop
	return
end try

-- Wait for servers to start
display notification "Starting services..." with title "BriefDesk Installer"
delay 3

-- Check if servers are running
set serverReady to false
repeat 10 times
	try
		do shell script "curl -s http://127.0.0.1:18765/debug > /dev/null"
		set serverReady to true
		exit repeat
	on error
		delay 1
	end try
end repeat

-- Success!
if serverReady then
	set successResult to display dialog "BriefDesk installed successfully!

The setup wizard will now open in your browser to help you configure your integrations (Slack, Calendar, etc.)

Tip: Set your browser homepage to:
http://127.0.0.1:8765/start.html" buttons {"Open Setup"} default button "Open Setup" with title "Installation Complete" with icon note
	
	-- Open setup page
	do shell script "open 'http://127.0.0.1:8765/setup.html'"
else
	display dialog "BriefDesk was installed but servers may still be starting.

Try opening manually:
http://127.0.0.1:8765/setup.html

Check logs at:
/tmp/briefdesk-server.log" buttons {"OK"} default button "OK" with title "Installation Complete" with icon caution
end if
