/**
 * Kaithem Board API Integration
 * Board-specific backend for load/save operations
 * Implements IBoardBackend for use with the Dashbeard editor
 */

import { BoardDefinition } from 'dashbeard/src/boards/board-types';
import type { IBoardBackend } from 'dashbeard/src/editor/types';

export class KaithemBoardAPI implements IBoardBackend {
  private boardId: string;

  constructor(boardId: string) {
    this.boardId = boardId;
  }

  /**
   * Load a board from Kaithem
   */
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

  /**
   * Save a board to Kaithem
   */
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

/**
 * Management API for board lifecycle operations
 * Separate from core backend to keep concerns isolated
 */
export class KaithemBoardManagement {
  /**
   * Create a new board in Kaithem
   */
  static async create(board: BoardDefinition): Promise<string> {
    try {
      const response = await fetch('/api/dashboards/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ board }),
      });

      if (!response.ok) {
        throw new Error(`Failed to create board: ${response.statusText}`);
      }

      const data = await response.json();
      if (data.error) {
        throw new Error(data.error);
      }

      return data.id as string;
    } catch (error) {
      console.error('Error creating board:', error);
      throw error;
    }
  }

  /**
   * Delete a board from Kaithem
   */
  static async delete(id: string): Promise<void> {
    try {
      const response = await fetch(
        `/api/dashboards/${encodeURIComponent(id)}/delete`,
        {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to delete board: ${response.statusText}`);
      }

      const data = await response.json();
      if (data.error) {
        throw new Error(data.error);
      }
    } catch (error) {
      console.error('Error deleting board:', error);
      throw error;
    }
  }

  /**
   * List all boards from Kaithem
   */
  static async list(): Promise<BoardDefinition[]> {
    try {
      const response = await fetch('/api/dashboards/list', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to list boards: ${response.statusText}`);
      }

      const data = await response.json();
      if (data.error) {
        throw new Error(data.error);
      }

      return data.boards as BoardDefinition[];
    } catch (error) {
      console.error('Error listing boards:', error);
      throw error;
    }
  }
}
