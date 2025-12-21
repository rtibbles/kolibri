/**
 * H5P Handler for sandboxed content.
 *
 * Handles H5P_ZIP content type.
 * Provides xAPI shim for learning record storage.
 *
 * Note: This handler currently delegates to the legacy H5P loading mechanism
 * in kolibri-sandbox. A future refactor will move the H5PRunner code here.
 */
import { SandboxHandler } from 'kolibri-sandbox';
import xAPIShim from './xAPIShim';

export default class H5PHandler extends SandboxHandler {
  /**
   * Shims required by H5P content.
   * - xAPI: For learning record storage
   */
  static shims = [xAPIShim];

  /**
   * Initialize the iframe with H5P content.
   *
   * @param {HTMLIFrameElement} iframe - The content iframe
   * @param {string} startUrl - URL to the H5P file
   * @param {Object} options - Initialization options
   * @param {string} options.contentNamespace - Namespace for content storage
   * @returns {Promise<void>}
   */
  async init(iframe, startUrl, options) {
    // H5P loading is handled by the existing H5PRunner mechanism
    // which is loaded from the legacy H5P/H5PInterface.
    // This handler provides the xAPI shim and will be expanded
    // in a future refactor to include the H5PRunner code.

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
        reject(new Error('Failed to load H5P content'));
      };

      // Navigate to the content URL
      iframe.src = startUrl;
    });
  }

  /**
   * Get progress from the xAPI shim if available.
   * @returns {number|null}
   */
  getProgress() {
    if (this.shims.xAPI) {
      return this.shims.xAPI.getProgress();
    }
    return null;
  }
}
