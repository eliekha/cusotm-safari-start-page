/**
 * Gmail API Client
 * 
 * Wraps the Gmail API for searching and reading emails.
 * All operations are READ-ONLY - no ability to send, modify, or delete.
 */

import { google, gmail_v1 } from 'googleapis';
import { OAuth2Client } from 'google-auth-library';

export interface Email {
  id: string;
  threadId: string;
  subject: string;
  from: string;
  to: string;
  date: string;
  snippet: string;
  labelIds: string[];
}

export interface EmailContent {
  id: string;
  threadId: string;
  subject: string;
  from: string;
  to: string;
  cc?: string;
  date: string;
  body: string;
  attachments: Array<{
    filename: string;
    mimeType: string;
    size: number;
  }>;
}

export interface SearchResult {
  emails: Email[];
  nextPageToken?: string;
  resultSizeEstimate: number;
}

/**
 * Gmail client for read-only operations
 */
export class GmailClient {
  private gmail: gmail_v1.Gmail;
  
  constructor(auth: OAuth2Client) {
    this.gmail = google.gmail({ version: 'v1', auth });
  }
  
  /**
   * Search for emails matching a query
   * Uses Gmail's search syntax (same as web interface)
   */
  async search(query: string, maxResults: number = 20): Promise<SearchResult> {
    const response = await this.gmail.users.messages.list({
      userId: 'me',
      q: query,
      maxResults: Math.min(maxResults, 100),
    });
    
    const messages = response.data.messages || [];
    const emails: Email[] = [];
    
    // Fetch details for each message (in parallel, limited batches)
    const batchSize = 10;
    for (let i = 0; i < messages.length; i += batchSize) {
      const batch = messages.slice(i, i + batchSize);
      const details = await Promise.all(
        batch.map(msg => this.getEmailSummary(msg.id!))
      );
      emails.push(...details.filter((e): e is Email => e !== null));
    }
    
    return {
      emails,
      nextPageToken: response.data.nextPageToken || undefined,
      resultSizeEstimate: response.data.resultSizeEstimate || 0,
    };
  }
  
  /**
   * List emails from inbox or specific label
   */
  async list(labelIds: string[] = ['INBOX'], maxResults: number = 20): Promise<SearchResult> {
    const response = await this.gmail.users.messages.list({
      userId: 'me',
      labelIds,
      maxResults: Math.min(maxResults, 100),
    });
    
    const messages = response.data.messages || [];
    const emails: Email[] = [];
    
    // Fetch details for each message
    const batchSize = 10;
    for (let i = 0; i < messages.length; i += batchSize) {
      const batch = messages.slice(i, i + batchSize);
      const details = await Promise.all(
        batch.map(msg => this.getEmailSummary(msg.id!))
      );
      emails.push(...details.filter((e): e is Email => e !== null));
    }
    
    return {
      emails,
      nextPageToken: response.data.nextPageToken || undefined,
      resultSizeEstimate: response.data.resultSizeEstimate || 0,
    };
  }
  
  /**
   * Get email summary (headers only, no body)
   */
  private async getEmailSummary(messageId: string): Promise<Email | null> {
    try {
      const response = await this.gmail.users.messages.get({
        userId: 'me',
        id: messageId,
        format: 'metadata',
        metadataHeaders: ['Subject', 'From', 'To', 'Date'],
      });
      
      const msg = response.data;
      const headers = msg.payload?.headers || [];
      
      const getHeader = (name: string): string => {
        const header = headers.find(h => h.name?.toLowerCase() === name.toLowerCase());
        return header?.value || '';
      };
      
      return {
        id: msg.id!,
        threadId: msg.threadId!,
        subject: getHeader('Subject') || '(No Subject)',
        from: getHeader('From'),
        to: getHeader('To'),
        date: getHeader('Date'),
        snippet: msg.snippet || '',
        labelIds: msg.labelIds || [],
      };
    } catch (error) {
      console.error(`Failed to get email ${messageId}:`, error);
      return null;
    }
  }
  
  /**
   * Read full email content
   */
  async readEmail(messageId: string): Promise<EmailContent> {
    const response = await this.gmail.users.messages.get({
      userId: 'me',
      id: messageId,
      format: 'full',
    });
    
    const msg = response.data;
    const headers = msg.payload?.headers || [];
    
    const getHeader = (name: string): string => {
      const header = headers.find(h => h.name?.toLowerCase() === name.toLowerCase());
      return header?.value || '';
    };
    
    // Extract body
    const body = this.extractBody(msg.payload);
    
    // Extract attachments info
    const attachments = this.extractAttachments(msg.payload);
    
    return {
      id: msg.id!,
      threadId: msg.threadId!,
      subject: getHeader('Subject') || '(No Subject)',
      from: getHeader('From'),
      to: getHeader('To'),
      cc: getHeader('Cc') || undefined,
      date: getHeader('Date'),
      body,
      attachments,
    };
  }
  
  /**
   * Get thread (all messages in a conversation)
   */
  async getThread(threadId: string): Promise<EmailContent[]> {
    const response = await this.gmail.users.threads.get({
      userId: 'me',
      id: threadId,
      format: 'full',
    });
    
    const messages = response.data.messages || [];
    return messages.map(msg => {
      const headers = msg.payload?.headers || [];
      
      const getHeader = (name: string): string => {
        const header = headers.find(h => h.name?.toLowerCase() === name.toLowerCase());
        return header?.value || '';
      };
      
      return {
        id: msg.id!,
        threadId: msg.threadId!,
        subject: getHeader('Subject') || '(No Subject)',
        from: getHeader('From'),
        to: getHeader('To'),
        cc: getHeader('Cc') || undefined,
        date: getHeader('Date'),
        body: this.extractBody(msg.payload),
        attachments: this.extractAttachments(msg.payload),
      };
    });
  }
  
  /**
   * Extract body content from message payload
   */
  private extractBody(payload: gmail_v1.Schema$MessagePart | undefined): string {
    if (!payload) return '';
    
    // Try to get plain text body first
    if (payload.mimeType === 'text/plain' && payload.body?.data) {
      return this.decodeBase64(payload.body.data);
    }
    
    // Check for HTML body
    if (payload.mimeType === 'text/html' && payload.body?.data) {
      return this.htmlToText(this.decodeBase64(payload.body.data));
    }
    
    // Handle multipart messages
    if (payload.parts) {
      // Prefer plain text
      const textPart = payload.parts.find(p => p.mimeType === 'text/plain');
      if (textPart?.body?.data) {
        return this.decodeBase64(textPart.body.data);
      }
      
      // Fall back to HTML
      const htmlPart = payload.parts.find(p => p.mimeType === 'text/html');
      if (htmlPart?.body?.data) {
        return this.htmlToText(this.decodeBase64(htmlPart.body.data));
      }
      
      // Recursively check nested parts
      for (const part of payload.parts) {
        const nestedBody = this.extractBody(part);
        if (nestedBody) return nestedBody;
      }
    }
    
    return '';
  }
  
  /**
   * Extract attachment info from message payload
   */
  private extractAttachments(payload: gmail_v1.Schema$MessagePart | undefined): Array<{
    filename: string;
    mimeType: string;
    size: number;
  }> {
    const attachments: Array<{ filename: string; mimeType: string; size: number }> = [];
    
    if (!payload) return attachments;
    
    // Check this part
    if (payload.filename && payload.body?.attachmentId) {
      attachments.push({
        filename: payload.filename,
        mimeType: payload.mimeType || 'application/octet-stream',
        size: payload.body.size || 0,
      });
    }
    
    // Check nested parts
    if (payload.parts) {
      for (const part of payload.parts) {
        attachments.push(...this.extractAttachments(part));
      }
    }
    
    return attachments;
  }
  
  /**
   * Decode base64url encoded string
   */
  private decodeBase64(data: string): string {
    // Gmail uses base64url encoding
    const base64 = data.replace(/-/g, '+').replace(/_/g, '/');
    return Buffer.from(base64, 'base64').toString('utf-8');
  }
  
  /**
   * Convert HTML to plain text (simple implementation)
   */
  private htmlToText(html: string): string {
    return html
      // Remove scripts and styles
      .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
      // Convert block elements to newlines
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(p|div|h[1-6]|li|tr)>/gi, '\n')
      .replace(/<(p|div|h[1-6]|li|tr)[^>]*>/gi, '\n')
      // Remove remaining tags
      .replace(/<[^>]+>/g, '')
      // Decode HTML entities
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      // Clean up whitespace
      .replace(/\n\s*\n/g, '\n\n')
      .trim();
  }
  
  /**
   * Get available labels
   */
  async getLabels(): Promise<Array<{ id: string; name: string; type: string }>> {
    const response = await this.gmail.users.labels.list({
      userId: 'me',
    });
    
    return (response.data.labels || []).map(label => ({
      id: label.id!,
      name: label.name!,
      type: label.type || 'user',
    }));
  }
}
