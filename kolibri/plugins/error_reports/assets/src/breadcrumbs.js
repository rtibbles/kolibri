const MAX_BREADCRUMBS = 30;
const breadcrumbs = [];

// Store TRUE original methods at module load time (before any wrapping)
const trueOriginalXhrOpen =
  typeof XMLHttpRequest !== 'undefined' ? XMLHttpRequest.prototype.open : null;
const trueOriginalXhrSend =
  typeof XMLHttpRequest !== 'undefined' ? XMLHttpRequest.prototype.send : null;

// Store original methods for restoration/chaining (saved once, never overwritten)
let originalConsoleMethods = null;
let originalFetch = null;
let originalXhrOpen = null;
let originalXhrSend = null;
let initialized = false;

// For testing - reset initialization state (but don't unwrap - methods stay wrapped)
export function _resetInitialized() {
  initialized = false;
}

// For testing - fully reset wrapper state (allows re-wrapping)
export function _resetWrappers() {
  originalConsoleMethods = null;
  originalFetch = null;
  originalXhrOpen = null;
  originalXhrSend = null;
  initialized = false;
  // Restore XHR prototype methods to their true originals
  if (typeof XMLHttpRequest !== 'undefined') {
    if (trueOriginalXhrOpen) {
      XMLHttpRequest.prototype.open = trueOriginalXhrOpen;
    }
    if (trueOriginalXhrSend) {
      XMLHttpRequest.prototype.send = trueOriginalXhrSend;
    }
  }
}

export function addBreadcrumb(type, category, data) {
  breadcrumbs.push({
    type,
    category,
    data,
    timestamp: Date.now(),
  });
  if (breadcrumbs.length > MAX_BREADCRUMBS) {
    breadcrumbs.shift();
  }
}

export function getBreadcrumbs() {
  return [...breadcrumbs];
}

export function clearBreadcrumbs() {
  breadcrumbs.length = 0;
}

function wrapConsole() {
  // Only wrap once - if originalConsoleMethods is already set, we've already wrapped
  if (originalConsoleMethods) return;

  originalConsoleMethods = {};
  ['log', 'warn', 'error', 'info'].forEach(level => {
    originalConsoleMethods[level] = console[level];
    console[level] = function (...args) {
      addBreadcrumb('console', level, {
        message: args
          .map(a => {
            try {
              return String(a);
            } catch {
              return '[Object]';
            }
          })
          .join(' ')
          .slice(0, 200),
      });
      originalConsoleMethods[level].apply(console, args);
    };
  });
}

function setupClickListener() {
  document.addEventListener(
    'click',
    e => {
      const target = e.target;
      if (!target || !target.tagName) return;

      addBreadcrumb('ui', 'click', {
        tag: target.tagName,
        id: target.id || undefined,
        className: (target.className || '').toString().slice(0, 100),
        text: (target.textContent || '').slice(0, 50),
      });
    },
    { capture: true, passive: true }
  );
}

function wrapFetch() {
  // Only wrap once
  if (originalFetch) return;
  if (typeof window.fetch !== 'function') return;

  originalFetch = window.fetch;
  window.fetch = function (url, options = {}) {
    const method = options.method || 'GET';
    addBreadcrumb('http', 'fetch', {
      method,
      url: String(url).slice(0, 200),
    });
    return originalFetch.apply(this, arguments);
  };
}

function wrapXhr() {
  // Only wrap once
  if (originalXhrOpen) return;
  if (typeof XMLHttpRequest === 'undefined') return;

  originalXhrOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this._breadcrumbData = {
      method,
      url: String(url).slice(0, 200),
    };
    return originalXhrOpen.apply(this, arguments);
  };

  originalXhrSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    if (this._breadcrumbData) {
      addBreadcrumb('http', 'xhr', this._breadcrumbData);
    }
    return originalXhrSend.apply(this, arguments);
  };
}

function setupRouterListener(router) {
  if (!router || typeof router.afterEach !== 'function') return;

  router.afterEach((to, from) => {
    addBreadcrumb('navigation', 'route', {
      from: from.fullPath,
      to: to.fullPath,
      name: to.name,
    });
  });
}

export function initBreadcrumbs(router = null) {
  if (initialized) return;
  initialized = true;

  wrapConsole();
  setupClickListener();
  wrapFetch();
  wrapXhr();
  setupRouterListener(router);
}
