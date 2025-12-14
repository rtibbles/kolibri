import Vue from 'vue';
import logging from 'kolibri-logging';
import router from 'kolibri/router';
import {
  report,
  VueErrorReport,
  JavascriptErrorReport,
  UnhandledRejectionErrorReport,
} from './utils';
import { initBreadcrumbs } from './breadcrumbs';
import { initErrorQueue } from './errorQueue';

const logger = logging.getLogger(__filename);

// Initialize breadcrumb collection with router for navigation tracking
initBreadcrumbs(router);

// Initialize error queue for offline support and deduplication
initErrorQueue();

// These shall be responsible for catching runtime errors
Vue.config.errorHandler = function (err, vm) {
  logger.debug(`Unexpected Error: ${err}`);
  const error = new VueErrorReport(err, vm);
  report(error);
};

window.addEventListener('error', e => {
  logger.debug(`Unexpected Error: ${e.error}`);
  const error = new JavascriptErrorReport(e);
  report(error);
});

window.addEventListener('unhandledrejection', event => {
  if (process.env.NODE_ENV === 'production') {
    event.preventDefault();
  }
  logger.debug(`Unhandled Rejection: ${event}`);
  const error = new UnhandledRejectionErrorReport(event);
  report(error);
});
