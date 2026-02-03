/**
 * Google Drive API Client
 * 
 * Wraps the Google Drive API for searching and reading files.
 * All operations are read-only.
 */

import { google, drive_v3 } from 'googleapis';
import { OAuth2Client } from 'google-auth-library';

export interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  webViewLink?: string;
  modifiedTime?: string;
  size?: string;
  parents?: string[];
}

export interface SearchResult {
  files: DriveFile[];
  nextPageToken?: string;
}

export interface FileContent {
  content: string;
  mimeType: string;
  name: string;
}

/**
 * Google Drive client for read-only operations
 */
export class DriveClient {
  private drive: drive_v3.Drive;
  
  constructor(auth: OAuth2Client) {
    this.drive = google.drive({ version: 'v3', auth });
  }
  
  /**
   * Search for files matching a query
   * Uses Google Drive's full-text search with smart query parsing
   */
  async search(query: string, maxResults: number = 20): Promise<SearchResult> {
    // Build smart search query - searches file content AND name
    // Split query into words for better matching (finds docs containing all words, not just exact phrase)
    const words = query
      .replace(/'/g, "\\'")
      .split(/\s+/)
      .filter(w => w.length > 2); // Skip very short words
    
    let q: string;
    if (words.length === 0) {
      // Fallback to original query if no valid words
      q = `fullText contains '${query.replace(/'/g, "\\'")}' and trashed = false`;
    } else if (words.length === 1) {
      // Single word - simple search
      q = `fullText contains '${words[0]}' and trashed = false`;
    } else {
      // Multiple words - require all words to be present (AND logic)
      // This finds documents containing all the search terms anywhere in content
      const wordClauses = words.map(w => `fullText contains '${w}'`).join(' and ');
      q = `(${wordClauses}) and trashed = false`;
    }
    
    const response = await this.drive.files.list({
      q,
      pageSize: maxResults,
      fields: 'nextPageToken, files(id, name, mimeType, webViewLink, modifiedTime, size, parents)',
      orderBy: 'modifiedTime desc',
    });
    
    return {
      files: (response.data.files || []) as DriveFile[],
      nextPageToken: response.data.nextPageToken || undefined,
    };
  }
  
  /**
   * List files in a specific folder
   */
  async listFolder(folderId: string = 'root', maxResults: number = 50): Promise<SearchResult> {
    const response = await this.drive.files.list({
      q: `'${folderId}' in parents and trashed = false`,
      pageSize: maxResults,
      fields: 'nextPageToken, files(id, name, mimeType, webViewLink, modifiedTime, size, parents)',
      orderBy: 'name',
    });
    
    return {
      files: (response.data.files || []) as DriveFile[],
      nextPageToken: response.data.nextPageToken || undefined,
    };
  }
  
  /**
   * Get file metadata by ID
   */
  async getFile(fileId: string): Promise<DriveFile> {
    const response = await this.drive.files.get({
      fileId,
      fields: 'id, name, mimeType, webViewLink, modifiedTime, size, parents',
    });
    
    return response.data as DriveFile;
  }
  
  /**
   * Read file content
   * Automatically exports Google Workspace files to readable formats
   */
  async readFile(fileId: string): Promise<FileContent> {
    // First get file metadata to determine type
    const file = await this.getFile(fileId);
    const mimeType = file.mimeType;
    
    // Handle Google Workspace files - export to readable format
    if (mimeType.startsWith('application/vnd.google-apps.')) {
      return this.exportGoogleFile(fileId, file.name, mimeType);
    }
    
    // Regular files - download content
    const response = await this.drive.files.get({
      fileId,
      alt: 'media',
    }, {
      responseType: 'text',
    });
    
    return {
      content: response.data as string,
      mimeType: file.mimeType,
      name: file.name,
    };
  }
  
  /**
   * Export Google Workspace files to readable formats
   */
  private async exportGoogleFile(fileId: string, name: string, mimeType: string): Promise<FileContent> {
    let exportMimeType: string;
    let outputMimeType: string;
    
    switch (mimeType) {
      case 'application/vnd.google-apps.document':
        // Google Docs -> Markdown
        exportMimeType = 'text/markdown';
        outputMimeType = 'text/markdown';
        break;
        
      case 'application/vnd.google-apps.spreadsheet':
        // Google Sheets -> CSV
        exportMimeType = 'text/csv';
        outputMimeType = 'text/csv';
        break;
        
      case 'application/vnd.google-apps.presentation':
        // Google Slides -> Plain text
        exportMimeType = 'text/plain';
        outputMimeType = 'text/plain';
        break;
        
      case 'application/vnd.google-apps.drawing':
        // Google Drawings -> PNG (return as base64)
        exportMimeType = 'image/png';
        outputMimeType = 'image/png';
        break;
        
      default:
        // Try plain text for other Google types
        exportMimeType = 'text/plain';
        outputMimeType = 'text/plain';
    }
    
    const response = await this.drive.files.export({
      fileId,
      mimeType: exportMimeType,
    }, {
      responseType: exportMimeType.startsWith('image/') ? 'arraybuffer' : 'text',
    });
    
    let content: string;
    if (exportMimeType.startsWith('image/')) {
      // Convert binary to base64
      const buffer = Buffer.from(response.data as ArrayBuffer);
      content = `data:${exportMimeType};base64,${buffer.toString('base64')}`;
    } else {
      content = response.data as string;
    }
    
    return {
      content,
      mimeType: outputMimeType,
      name,
    };
  }
  
  /**
   * Get file web view URL
   */
  getWebViewUrl(file: DriveFile): string {
    if (file.webViewLink) {
      return file.webViewLink;
    }
    return `https://drive.google.com/file/d/${file.id}/view`;
  }
}
