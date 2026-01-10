# Projection Mapper Builder

A core plugin for KaithemAutomation that provides real-time collaborative
projection mapping with WebSocket-based multi-device synchronization.

## Features

- **Projection Mapping**: Position and transform iframe sources with four-point
  perspective correction
- **Real-time Collaboration**: Edit on phone while controlling a projector
  simultaneously via WebSocket
- **VFX Effects**: Apply effects like glitch, CRT, film grain, RGB shift,
  kaleidoscope, and pixelate
- **Touch-friendly UI**: Mobile-optimized controls for dragging corners
- **Guest Viewer**: Full-screen presentation mode accessible without auth
- **Atomic Saves**: VFX and source changes save atomically; transforms sync
  in real-time during dragging

## Usage

### Creating a Projection

1. Create a new "Projection Mapper" resource
2. Click Edit to open the editor
3. Add sources (iframes) with "Add Source" button
4. Position sources by dragging corners in the canvas
5. Adjust opacity, blend mode, and rotation in sidebar
6. Add VFX effects from the Effects panel
7. Click Save to persist changes

### Multi-Device Workflow

1. Open editor on your control device (phone/tablet)
2. Open editor or viewer on presentation device (projector)
3. Position sources on control device - updates appear in real-time on projector
4. Make other changes (effects, sources) and click Save

### Viewer Mode

- Accessible without authentication at `/projection-mapper/view/{module}/{resource}`
- Suitable for public displays and signage
- Receives real-time transform updates from any editor session
- Full-screen, no UI chrome

## Technical Details

### URL Routes

- Editor (authenticated): `/projection-mapper/editor/{module}/{resource}`
- Viewer (guest): `/projection-mapper/view/{module}/{resource}`
- API data: `/projection-mapper/api/data/{module}/{resource}`
- API save: `/projection-mapper/api/save/{module}/{resource}`
- WebSocket sync: `/projection-mapper/ws/{module}/{resource}`

### Resource Schema

```yaml
title: "Projection Name"
sources:
  - id: "src1"
    name: "Source Name"
    type: "iframe"
    config:
      url: "https://example.com"
    transform:
      corners:
        tl: {x: 0, y: 0}
        tr: {x: 1920, y: 0}
        bl: {x: 0, y: 1080}
        br: {x: 1920, y: 1080}
      opacity: 1.0
      blend_mode: "normal"
      rotation: 0
    vfx:
      - shader: "glitch"
        params: {amount: 0.5}
    visible: true
```

### WebSocket Protocol

Transform updates (real-time):
```json
{
  "source_id": "src1",
  "corners": {
    "tl": {"x": 100, "y": 100},
    "tr": {"x": 500, "y": 100},
    "bl": {"x": 100, "y": 400},
    "br": {"x": 500, "y": 400}
  }
}
```

Reload signal (after Save):
```json
{
  "type": "reload"
}
```

## Implementation Notes

### Current Limitations

- Perspective transform uses simplified matrix calculation (identity matrix)
  - Full OpenCV-style homography calculation should be implemented
  - Consider using perspective.js or similar library
- VFX effects are minimal implementations (glitch, CRT, etc.)
  - Consider integrating full VFX-JS library from https://github.com/fand/vfx-js
- Single iframe source type currently supported
  - Extensible design ready for video, image, canvas sources

### Future Enhancements

1. Proper perspective transform using homography matrix
2. Full VFX-JS integration with all effects
3. Additional source types: video, image, canvas
4. Effect preview in editor
5. Keyboard shortcuts (pan/zoom)
6. Undo/redo support
7. Transition effects for source enter/exit
8. Advanced blend modes
9. Preset saving/loading
10. Multi-canvas rendering optimization

## Files

- `__init__.py` - Plugin entry point and routes
- `html/editor.html` - Editor template
- `html/viewer.html` - Viewer template
- `static/projection-editor.js` - Editor application logic
- `static/projection-mapper.css` - Styles (80 char compliant)
- `static/vfx-js/vfx.esm.js` - VFX effects library

## Style Guide Compliance

- 80 character line limit throughout
- Spaces not tabs
- No hand-formatted code
- Type hints where applicable
- Modular, readable structure

## Architecture

### Resource Type

`ProjectionMapperType` extends `modules_state.ResourceType` with:
- JSON schema for validation
- Lifecycle handlers (on_load, on_update, on_unload)
- Edit page redirecting to full-page editor
- Blurb showing editor/viewer links

### Editor

Vanilla JavaScript application (not Vue):
- Canvas-based preview with corner handles
- Sidebar for source list and transform controls
- Real-time WebSocket communication
- Touch-friendly controls (20px hit radius)

### Viewer

WebGL-optimized rendering with:
- Full-screen canvas
- Real-time WebSocket sync
- VFX effect pipeline
- CSS transform perspective
- Guest authentication

### WebSocket Sync

- One connection per resource per client
- MessageBus for broadcasting to all connected clients
- Only corner positions sync in real-time
- Other changes require atomic Save
- Automatic reconnection with 3s delay

## License

SPDX-FileCopyrightText: Copyright Daniel Dunn
SPDX-License-Identifier: GPL-3.0-or-later
