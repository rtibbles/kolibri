/**
 * Base class for sandbox handlers.
 *
 * Handlers are content-type-specific code that runs inside the sandboxed iframe.
 * They are responsible for initializing and managing content rendering.
 *
 * Usage:
 *   import { SandboxHandler } from 'kolibri-sandbox';
 *
 *   export default class MyHandler extends SandboxHandler {
 *     static shims = [MyShim];
 *
 *     async init(iframe, startUrl, options) {
 *       // Initialize content
 *     }
 *   }
 *
 * The handler self-registers with the sandbox environment when instantiated.
 * Handler scripts should instantiate their handler class at the module level:
 *
 *   new MyHandler(window.SandboxEnvironment);
 */
import { SandboxShim } from './SandboxShim';

export class SandboxHandler {
  /**
   * Array of SandboxShim subclasses this handler requires.
   * Override in subclass.
   * @type {Array<typeof SandboxShim>}
   */
  static shims = [];

  /**
   * @param {SandboxEnvironment} sandbox - The sandbox environment instance
   */
  constructor(sandbox) {
    if (!sandbox) {
      throw new Error(
        'SandboxHandler requires a sandbox environment. ' +
          'Pass window.SandboxEnvironment when instantiating.',
      );
    }

    this.sandbox = sandbox;
    this.mediator = sandbox.mediator;
    this.shims = {};

    // Instantiate declared shims
    for (const ShimClass of this.constructor.shims) {
      if (!ShimClass.shimName) {
        throw new Error(`Shim class ${ShimClass.name} must define static shimName`);
      }
      const shim = new ShimClass(this.mediator);
      this.shims[ShimClass.shimName] = shim;
    }

    // Self-register with sandbox
    sandbox._registerHandler(this);
  }

  /**
   * Initialize content in the iframe.
   * Override in subclass.
   *
   * @param {HTMLIFrameElement} iframe - The content iframe
   * @param {string} startUrl - URL to the content entry point
   * @param {Object} options - Initialization options
   * @param {string} options.contentNamespace - Namespace for content storage
   * @returns {Promise<void>}
   */
  async init(iframe, startUrl, options) {
    throw new Error('Subclass must implement init()');
  }

  /**
   * Clean up resources when content is unloaded.
   * Override in subclass if cleanup is needed.
   */
  destroy() {}

  /**
   * Called by sandbox to initialize shims on the content window.
   * @param {Window} contentWindow - The iframe's content window
   * @private
   */
  _initializeShims(contentWindow) {
    for (const shim of Object.values(this.shims)) {
      try {
        shim.iframeInitialize(contentWindow);
      } catch (e) {
        console.error(`Failed to initialize shim ${shim.constructor.shimName}:`, e); // eslint-disable-line no-console
      }
    }
  }

  /**
   * Calculate progress from shims.
   * Returns the first non-null progress value from shims.
   * @returns {number|null}
   */
  getProgress() {
    for (const shim of Object.values(this.shims)) {
      if (typeof shim.getProgress === 'function') {
        const progress = shim.getProgress();
        if (progress !== null) {
          return progress;
        }
      }
    }
    return null;
  }

  /**
   * Collect state data from all shims for persistence.
   * @returns {Object} Combined state data keyed by shim name
   */
  getData() {
    const data = {};
    for (const [name, shim] of Object.entries(this.shims)) {
      if (shim.data !== undefined) {
        data[name] = shim.data;
      }
    }
    return data;
  }

  /**
   * Restore state data to shims.
   * @param {Object} data - State data keyed by shim name
   */
  setData(data) {
    if (!data) return;
    for (const [name, shimData] of Object.entries(data)) {
      if (this.shims[name] && typeof this.shims[name].setData === 'function') {
        this.shims[name].setData(shimData);
      }
    }
  }

  /**
   * Set user data on all shims.
   * @param {Object} userData - User data object
   */
  setUserData(userData) {
    for (const shim of Object.values(this.shims)) {
      if (typeof shim.setUserData === 'function') {
        shim.setUserData(userData);
      }
    }
  }
}

export default SandboxHandler;
