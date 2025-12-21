/**
 * H5P Handler for sandboxed content.
 *
 * Handles H5P_ZIP content type using H5PRunner for content loading.
 * Provides xAPI shim for learning record storage.
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
   * @returns {Promise<void>}
   */
  async init(iframe, startUrl, options) {
    // Dynamically import H5PRunner to reduce initial bundle size
    const { default: H5PRunner } = await import(
      /* webpackChunkName: "H5PRunner" */ './H5PRunner'
    );

    return new Promise((resolve, reject) => {
      this.runner = new H5PRunner(this.shims.xAPI);
      this.runner.init(iframe, startUrl, resolve, reject);
    });
  }

  /**
   * Clean up resources when content is unloaded.
   */
  destroy() {
    this.runner = null;
  }

  /**
   * Called by sandbox to initialize shims on the content window.
   * H5P has special initialization via shimH5PIntegration.
   * @param {Window} contentWindow - The iframe's content window
   * @private
   */
  _initializeShims(contentWindow) {
    super._initializeShims(contentWindow);
    if (this.runner) {
      this.runner.shimH5PIntegration(contentWindow);
    }
  }
}
