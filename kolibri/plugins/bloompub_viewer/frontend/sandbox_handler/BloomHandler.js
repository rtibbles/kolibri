/**
 * Bloompub Handler for sandboxed content.
 *
 * Handles BLOOMPUB content type.
 * Provides BloomShim for progress tracking.
 *
 * Note: This handler currently delegates to the legacy Bloom loading mechanism
 * in kolibri-sandbox. A future refactor will move the BloomRunner code here.
 */
import { SandboxHandler } from 'kolibri-sandbox';
import BloomShim from './BloomShim';

export default class BloomHandler extends SandboxHandler {
  /**
   * Shims required by Bloompub content.
   * - BloomPlayer: For progress tracking via page reads
   */
  static shims = [BloomShim];

  /**
   * Initialize the iframe with Bloompub content.
   *
   * @param {HTMLIFrameElement} iframe - The content iframe
   * @param {string} startUrl - URL to the Bloompub file
   * @param {Object} options - Initialization options
   * @param {string} options.contentNamespace - Namespace for content storage
   * @returns {Promise<void>}
   */
  async init(iframe, startUrl, options) {
    return new Promise((resolve, reject) => {
      iframe.onload = () => {
        const error = iframe.contentDocument?.head?.querySelector('meta[name="sandbox-error"]');
        if (error) {
          reject(new Error(error.getAttribute('content')));
        } else {
          resolve();
        }
      };

      iframe.onerror = () => {
        reject(new Error('Failed to load Bloompub content'));
      };

      // Navigate to the content URL
      iframe.src = startUrl;
    });
  }

  /**
   * Get progress from the BloomShim if available.
   * @returns {number|null}
   */
  getProgress() {
    if (this.shims.BloomPlayer) {
      return this.shims.BloomPlayer.getProgress();
    }
    return null;
  }
}
