# CorePluginWebConsole

Web-based terminal emulator for Kaithem using xterm.js.

## Features

- **Full terminal emulation** with xterm.js 5.3.0
- **Image support** via the xterm-addon-image
- **Clipboard integration** via the xterm-addon-clipboard
- **Auto-resizing** terminal that fits the browser window
- **Clickable web links** in terminal output
- **Security**: Requires `system_admin` permission - absolutely no access without admin rights
- **Modular design**: Can accept custom WebSocket URLs for other terminal-like endpoints

## Usage

### Basic Usage

Navigate to `/webconsole` in your Kaithem instance. You must be logged in as an administrator.

### Custom WebSocket URL

The terminal UI is designed to be modular. You can specify a custom WebSocket URL as a query parameter:

```
/webconsole?ws=/path/to/your/websocket
```

This allows you to create other terminal-like endpoints and reuse the same UI.

## Security

**CRITICAL**: This plugin requires `system_admin` permission for both the UI and WebSocket endpoints. The terminal has full shell access to the server, so it must never be accessible to non-admin users.

Both the web page endpoint and the WebSocket endpoint verify admin permissions using `require("system_admin")`.

## Technical Details

### Backend

- Uses Python's `pty` module to create pseudo-terminals
- Forks a shell process (respects `$SHELL` environment variable, defaults to `/bin/bash`)
- Handles binary and text data over WebSocket
- Supports terminal resize messages in format: `resize:cols:rows`

### Frontend

- xterm.js with modern terminal features
- VS Code-like color theme
- Auto-reconnection on connection loss (up to 5 attempts)
- Responsive design that adapts to window size
- Addons:
  - **FitAddon**: Auto-resize terminal to fit window
  - **WebLinksAddon**: Make URLs clickable
  - **ImageAddon**: Display images in terminal
  - **ClipboardAddon**: Enhanced clipboard support

## Endpoints

- `GET /webconsole` - Terminal UI page (admin only)
- `WS /webconsole/terminal` - WebSocket for terminal communication (admin only)

## Future Enhancements

The modular design allows for future terminal-like endpoints:
- SSH connections to remote systems
- Docker container shells
- Custom REPL environments
- Process output streaming

Simply create a new WebSocket endpoint and pass its URL to the terminal UI.
