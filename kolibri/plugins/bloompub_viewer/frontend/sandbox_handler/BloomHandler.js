/**
 * Bloompub Handler for sandboxed content.
 *
 * Handles BLOOMPUB content type using BloomRunner for content loading.
 * Provides BloomShim for progress tracking.
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
   * @returns {Promise<void>}
   */
  async init(iframe, startUrl, options) {
    // Dynamically import BloomRunner to reduce initial bundle size
    const { default: BloomRunner } = await import(
      /* webpackChunkName: "BloomRunner" */ './BloomRunner'
    );

    return new Promise((resolve, reject) => {
      this.runner = new BloomRunner(this.shims.BloomPlayer);
      this.runner.init(iframe, startUrl, resolve, reject);
    });
  }

  /**
   * Clean up resources when content is unloaded.
   */
  destroy() {
    this.runner = null;
  }

  // Note: Bloom Player gets its configuration via URL parameters,
  // not from global objects like H5P. No _initializeShims override needed.
}
