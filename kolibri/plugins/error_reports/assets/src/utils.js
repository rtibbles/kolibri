import { browser, os, device, isTouchDevice } from 'kolibri/utils/browserInfo';
import router from 'kolibri/router';
import { getBreadcrumbs } from './breadcrumbs';
import { report as queueAndReport } from './errorQueue';

const SCROLL_BAR = 16;
const widthBreakpoints = [
  480,
  600,
  840,
  960 - SCROLL_BAR,
  1280 - SCROLL_BAR,
  1440 - SCROLL_BAR,
  1600 - SCROLL_BAR,
];

export function getWindowBreakpoint(width = window.innerWidth) {
  for (const bp of widthBreakpoints) {
    if (width <= bp) return bp;
  }
  return widthBreakpoints[widthBreakpoints.length - 1];
}

/**
 * Report an error - queues and attempts to send
 */
export function report(error) {
  const data = error.getErrorReport();
  return queueAndReport(data);
}

class ErrorReport {
  constructor(e) {
    this.message = e?.message || 'Unknown Error';
    this.stack = e?.stack || 'No stack trace available';
  }

  getErrorReport() {
    return {
      error_message: this.message,
      traceback: this.stack,
      context: this.getContext(),
    };
  }

  getContext() {
    return {
      browser: browser,
      os: os,
      device: {
        ...device,
        is_touch_device: isTouchDevice,
        screen_breakpoint: getWindowBreakpoint(),
      },
      route: this._getRouteContext(),
      page: {
        url: window.location.href,
        visible: document.visibilityState === 'visible',
      },
      breadcrumbs: getBreadcrumbs(),
      ...this.getExtraContext(),
    };
  }

  _getRouteContext() {
    try {
      const route = router.currentRoute;
      if (!route) return null;
      return {
        name: route.name,
        path: route.path,
        params: route.params,
      };
    } catch {
      return null;
    }
  }

  getExtraContext() {
    return {};
  }
}

export class VueErrorReport extends ErrorReport {
  constructor(e, vm) {
    super(e);
    this.vm = vm;
  }

  getExtraContext() {
    return {
      component: {
        name:
          this.vm.$options.name || this.vm.$options._componentTag || 'Unknown Component',
        parents: this._getParentChain(this.vm, 5),
        props: this._sanitizeProps(this.vm.$props),
      },
    };
  }

  _getParentChain(vm, maxDepth) {
    const chain = [];
    let current = vm.$parent;
    while (current && chain.length < maxDepth) {
      chain.push(
        current.$options.name || current.$options._componentTag || 'Anonymous'
      );
      current = current.$parent;
    }
    return chain;
  }

  _sanitizeProps(props) {
    if (!props) return {};
    const sanitized = {};
    for (const [key, value] of Object.entries(props)) {
      if (typeof value === 'function') continue;
      if (typeof value === 'object' && value !== null) {
        sanitized[key] = '[Object]';
      } else {
        sanitized[key] = value;
      }
    }
    return sanitized;
  }
}

export class JavascriptErrorReport extends ErrorReport {
  constructor(e) {
    super(e.error || { message: e.message });
  }
}

export class UnhandledRejectionErrorReport extends ErrorReport {
  constructor(e) {
    super(e.reason);
  }
}
