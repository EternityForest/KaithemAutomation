/**
 * Kaithem Board API Integration
 * Board-specific backend for load/save operations
 * Implements IBoardBackend for use with the Dashbeard editor
 */

import { BoardDefinition } from 'dashbeard/src/boards/board-types.ts';
import type { FileMetadata, IBoardBackend, SystemTheme } from 'dashbeard/src/editor/types.ts';
import { kaithemapi } from '/static/js/widget.mjs';

export class KaithemBoardAPI implements IBoardBackend {
  private boardId: string;

  private ignoreCount = 0;

  constructor(boardId: string) {
    this.boardId = boardId;

    kaithemapi.subscribe(boardId + "-refresher", () => {
      if(this.ignoreCount > 0) {
        this.ignoreCount--;
        return;
      }
      globalThis.location.reload();
    });
    
  }


  async listResourceFolder(folder: string): Promise<FileMetadata[]> {
    // folder is a virtual path like "/board/subfolder" or "/public_resources"
    // Map to the backend list endpoint
    const response = await fetch(
      `/api/dashboards/${encodeURIComponent(this.boardId)}/files/list?path=${encodeURIComponent(folder)}`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );
    
    const result = await response.json();
    
    if (result.error) {
      throw new Error(result.error);
    }
    
    return result.resources || [];
  }

  async load(): Promise<BoardDefinition> {
    try {
      const response = await fetch(
        `/api/dashboards/${encodeURIComponent(this.boardId)}/load`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to load board: ${response.statusText}`);
      }

      const data = await response.json();
      if (data.error) {
        throw new Error(data.error);
      }

      return data.board as BoardDefinition;
    } catch (error) {
      console.error('Error loading board:', error);
      throw error;
    }
  }

  async save(board: BoardDefinition): Promise<void> {
    try {
      this.ignoreCount++;
      const response = await fetch(
        `/api/dashboards/${encodeURIComponent(this.boardId)}/save`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ board }),
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to save board: ${response.statusText}`);
      }

      const data = await response.json();
      if (data.error) {
        throw new Error(data.error);
      }
    } catch (error) {
      this.ignoreCount = 0;
      console.error('Error saving board:', error);
      throw error;
    }
  }

  async getSystemThemes(): Promise<SystemTheme[]> {
    try {
      const response = await fetch(
        `/api/dashboards/system-themes`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to get system themes: ${response.statusText}`);
      }

      const data = await response.json();
      if (data.error) {
        throw new Error(data.error);
      }

      return data.themes || [];
    } catch (error) {
      console.error('Error getting system themes:', error);
      return [];
    }
  }
}