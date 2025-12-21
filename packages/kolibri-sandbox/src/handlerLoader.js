/**
 * Utilities for loading handlers in the sandbox environment.
 */

/**
 * Load a handler script from a URL and wait for it to register.
 *
 * @param {string} url - URL to the handler script
 * @param {SandboxEnvironment} sandbox - The sandbox environment
 * @param {number} timeout - Timeout in milliseconds
 * @returns {Promise<void>}
 */
export function loadHandler(url, sandbox, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      reject(new Error(`Handler registration timeout after ${timeout}ms`));
    }, timeout);

    // Store resolver so _registerHandler can call it
    sandbox._handlerRegistrationResolver = () => {
      clearTimeout(timeoutId);
      resolve();
    };

    const script = document.createElement('script');
    script.src = url;
    script.onerror = () => {
      clearTimeout(timeoutId);
      sandbox._handlerRegistrationResolver = null;
      reject(new Error(`Failed to load handler script: ${url}`));
    };
    document.head.appendChild(script);
  });
}

export default { loadHandler };
