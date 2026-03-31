/**
 * Kaithem Board API Integration
 * Board-specific backend for load/save operations
 * Implements IBoardBackend for use with the Dashbeard editor
 */

import { BoardDefinition } from 'dashbeard/src/boards/board-types';
import type { FileMetadata, IBoardBackend } from 'dashbeard/src/editor/types';

export class KaithemBoardAPI implements IBoardBackend {
  private boardId: string;

  constructor(boardId: string) {
    this.boardId = boardId;
  }


  async listResourceFolder(folder: string): Promise<FileMetadata[]> {
        const response = await fetch(
        `/api/dashboards/${encodeURIComponent(this.boardId)}/files/get${folder}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }
        );
    
    return response.json();
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
      console.error('Error saving board:', error);
      throw error;
    }
  }
}