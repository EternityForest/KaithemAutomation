/**
 * Dashbeard Editor - Main Entry Point
 * Integrates with Kaithem for board persistence and API calls
 */

import { DashboardEditor } from '../../../../../Dashbeard/src/editor/components/dashboard-editor';
import { EditorState } from '../../../../../Dashbeard/src/editor/editor-state';
import { BoardDefinition } from '../../../../../Dashbeard/src/boards/board-types';
import { KaithemBoardAPI } from './kaithem-board-api';

/**
 * Extract module and resource names from URL path
 * Expects URL format: /static/vite/kaithem/src/plugins/CorePluginJackMixer/html/index.html?board={quote(module)}:{quote(resource)}
 */
function extractPathParameters(): { module: string; resource: string } {
  const urlParameters = new URLSearchParams(globalThis.location.search);
  const module = urlParameters.get('board')?.split(':')[0] || '';
  const resource = urlParameters.get('board')?.split(':')[1] || '';
  return { module, resource };
}

/**
 * Initialize the dashboard editor with Kaithem integration
 */
async function initializeDashboardEditor(): Promise<void> {
  try {
    const { module, resource } = extractPathParameters();

    // Create the editor element
    const editorElement = document.createElement('ds-dashboard-editor');
    const appContainer = document.getElementById('app');
    if (!appContainer) {
      throw new Error('App container not found');
    }
    appContainer.appendChild(editorElement);

    // Initialize the editor with Kaithem integration
    const boardAPI = new KaithemBoardAPI(module, resource);

    // Wait for the editor to be ready
    await customElements.whenDefined('ds-dashboard-editor');

    // Load the board from Kaithem
    const boardData = await boardAPI.loadBoard();

    // Initialize editor state
    const editorState = new EditorState(
      editorElement as unknown as DashboardEditor
    );
    editorState.module.set(module);
    editorState.resource.set(resource);
    editorState.setBoard(boardData);

    // Set up auto-save on dirty changes
    let saveTimeout: ReturnType<typeof setTimeout>;
    editorState.isDirty.subscribe((isDirty: boolean) => {
      if (isDirty) {
        // Debounce saves - wait 2 seconds after last change
        clearTimeout(saveTimeout);
        saveTimeout = setTimeout(async () => {
          const board = editorState.board.get();
          if (board) {
            try {
              await boardAPI.saveBoard(board);
              editorState.markClean();
            } catch (error) {
              console.error('Failed to save board:', error);
              alert('Failed to save board. Check console for details.');
            }
          }
        }, 2000);
      }
    });

    // Store editor state on element for component access
    (editorElement as any).editorState = editorState;

    console.log('Dashboard editor initialized for:', { module, resource });
  } catch (error) {
    console.error('Failed to initialize dashboard editor:', error);
    const appContainer = document.getElementById('app');
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
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeDashboardEditor);
} else {
  initializeDashboardEditor();
}
