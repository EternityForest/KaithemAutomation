/**
 * Dashbeard Editor - Main Entry Point
 * Integrates with Kaithem for board persistence and API calls
 */

import "dashbeard/src/editor/components/dashboard-editor.ts";
import { KaithemBoardAPI } from "./kaithem-board-api.ts";
import { createEditor, registerFormatDatalist } from "dashbeard/src/index.ts";
import type { IBoardBackend } from "dashbeard/src/editor/types.ts";
import { TagpointComponent } from "./tag-point.ts";
import { populateTagsDatalist } from "/static/js/widget.mjs";

/**
 * Extract module and resource names from URL path
 * Expects URL format: /static/vite/kaithem/src/plugins/CorePluginJackMixer/html/index.html?board={quote(module)}:{quote(resource)}
 */
function extractPathParameters(): { module: string; resource: string } {
  const urlParameters = new URLSearchParams(globalThis.location.search);
  const module = urlParameters.get("board")?.split(":")[0] || "";
  const resource = urlParameters.get("board")?.split(":")[1] || "";
  return { module, resource };
}

/**
 * Set up tag point autocomplete datalist for the "tagpoint" format
 */
async function setupTagpointDatalist(): Promise<void> {
  // Create the datalist element
  const datalist = document.createElement("datalist");
  datalist.id = "tagpoint-datalist";
  document.body.appendChild(datalist);

  // Populate with available tags
  await populateTagsDatalist(datalist);

  // Register the datalist for the "tagpoint" format
  registerFormatDatalist("tagpoint", "tagpoint-datalist");
}

/**
 * Initialize the dashboard editor with Kaithem integration
 */
async function initializeDashboardEditor(): Promise<void> {
  try {
    const { module, resource } = extractPathParameters();

    // Set up tag autocomplete before creating the editor
    await setupTagpointDatalist();

    // Create the editor element
    const appContainer = document.querySelector("#app");
    if (!appContainer || !(appContainer instanceof HTMLElement)) {
      throw new Error("App container not found");
    }

    // Initialize the editor with Kaithem integration
    const boardId = `dashboard-resource-${module}-${resource}`;
    const backend: IBoardBackend = new KaithemBoardAPI(boardId);

    // Create editor instance
    const editorObject = createEditor(appContainer, backend, true, {
      components:[TagpointComponent]
    });

    // Set up auto-save on dirty changes
    let saveTimeout: ReturnType<typeof setTimeout>;
    editorObject.editorState.isDirty.subscribe((isDirty: boolean) => {
      if (isDirty) {
        // Debounce saves - wait 120 seconds after last change
        clearTimeout(saveTimeout);
        saveTimeout = setTimeout(async () => {
          const board = editorObject.editorState.board.get();
          if (board) {
            await backend.save(board);
            editorObject.editorState.isDirty.set(false);
          }
        }, 120_000);
      }
    });

    console.log("Dashboard editor initialized for:", { module, resource });
  } catch (error) {
    console.error("Failed to initialize dashboard editor:", error);
    const appContainer = document.querySelector("#app");
    if (appContainer) {
      appContainer.innerHTML = `<div style="padding: 20px; color: red;">
        <h2>Error Loading Dashboard</h2>
        <p>${(error as Error).message}</p>
        <p>Check the browser console for more details.</p>
      </div>`;
    }
  }
}

// Start the application when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeDashboardEditor);
} else {
  initializeDashboardEditor();
}
