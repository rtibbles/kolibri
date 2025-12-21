/**
 * Base class for sandbox shims.
 *
 * Shims provide API compatibility layers for content running in the sandbox.
 * For example, xAPI or SCORM shims allow content to use these APIs while
 * the sandbox intercepts and handles the calls.
 *
 * This class extends the existing BaseShim to provide a cleaner API for
 * handler authors while maintaining backward compatibility.
 *
 * Usage:
 *   import { SandboxShim } from 'kolibri-sandbox';
 *
 *   export class MyShim extends SandboxShim {
 *     static shimName = 'myShim';
 *
 *     iframeInitialize(contentWindow) {
 *       contentWindow.myAPI = { ... };
 *     }
 *   }
 */
import BaseShim from './baseShim';

export class SandboxShim extends BaseShim {
  /**
   * Unique identifier for this shim.
   * Must be overridden in subclass.
   * @type {string}
   */
  static shimName = null;

  /**
   * @param {Mediator} mediator - The mediator instance for message passing
   */
  constructor(mediator) {
    super(mediator);

    if (!this.constructor.shimName) {
      throw new Error(`${this.constructor.name} must define static shimName`);
    }

    // Use shimName as the namespace for message passing
    this.nameSpace = this.constructor.shimName;
  }

  /**
   * Initialize the shim on the content window.
   * Override in subclass to patch APIs on the content window.
   *
   * @param {Window} contentWindow - The iframe's content window
   */
  iframeInitialize(contentWindow) {
    // Default implementation does nothing
    // Subclasses should override to set up their APIs
  }

  /**
   * Optional: Return progress calculated by this shim.
   * @returns {number|null} Progress value between 0 and 1, or null if not applicable
   */
  getProgress() {
    return null;
  }
}

export default SandboxShim;
