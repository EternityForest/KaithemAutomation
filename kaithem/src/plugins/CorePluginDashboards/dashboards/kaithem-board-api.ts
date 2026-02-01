/**
 * Kaithem Board API Integration
 * Handles all communication with the Kaithem backend for board operations
 */

import { BoardDefinition } from '../../../../../Dashbeard/src/boards/board-types';

export class KaithemBoardAPI {
  private module: string;
  private resource: string;

  constructor(module: string, resource: string) {
    this.module = module;
    this.resource = resource;
  }

  /**
   * Load a board from Kaithem
   */
  async loadBoard(): Promise<BoardDefinition> {
    try {
      const response = await fetch(
        `/api/dashboards/${encodeURIComponent(this.module)}/${encodeURIComponent(this.resource)}/load`,
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
  async saveBoard(board: BoardDefinition): Promise<void> {
    try {
      const response = await fetch(
        `/api/dashboards/${encodeURIComponent(this.module)}/${encodeURIComponent(this.resource)}/save`,
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

  /**
   * Delete a board from Kaithem
   */
  async deleteBoard(): Promise<void> {
    try {
      const response = await fetch(
        `/api/dashboards/${encodeURIComponent(this.module)}/${encodeURIComponent(this.resource)}/delete`,
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
   * Get the API base path for this board
   */
  getApiBasePath(): string {
    return `/api/dashboards/${encodeURIComponent(this.module)}/${encodeURIComponent(this.resource)}`;
  }
}
