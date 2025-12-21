/**
 * HTML5 Zip Handler for sandboxed content.
 *
 * Handles HTML5_ZIP and IMSCP_ZIP content types.
 * Provides SCORM and Kolibri data API shims.
 */
import { SandboxHandler } from 'kolibri-sandbox';
import SCORMShim from './SCORMShim';
import KolibriShim from './KolibriShim';

export default class Html5ZipHandler extends SandboxHandler {
  /**
   * Shims required by HTML5 zip content.
   * - SCORM: For SCORM-based learning content
   * - Kolibri: For accessing Kolibri content data
   */
  static shims = [SCORMShim, KolibriShim];

  /**
   * Initialize the iframe with HTML5 zip content.
   *
   * @param {HTMLIFrameElement} iframe - The content iframe
   * @param {string} startUrl - URL to the content entry point (zip file URL)
   * @param {Object} options - Initialization options
   * @param {string} options.contentNamespace - Namespace for content storage
   * @returns {Promise<void>}
   */
  async init(iframe, startUrl, options) {
    return new Promise((resolve, reject) => {
      // Set up the onload handler
      iframe.onload = () => {
        const error = iframe.contentDocument?.head?.querySelector('meta[name="sandbox-error"]');
        if (error) {
          reject(new Error(error.getAttribute('content')));
        } else {
          resolve();
        }
      };

      iframe.onerror = () => {
        reject(new Error('Failed to load content'));
      };

      // Navigate to the content URL
      iframe.src = startUrl;
    });
  }

  /**
   * Get progress from the SCORM shim if available.
   * @returns {number|null}
   */
  getProgress() {
    // Try SCORM shim first
    if (this.shims.SCORM) {
      const progress = this.shims.SCORM.getProgress();
      if (progress !== null) {
        return progress;
      }
    }
    return null;
  }
}
