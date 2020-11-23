import xAPI from './h5p-x-api';
import actionBar from './h5p-action-bar';
import contentType from './h5p-content-type';
import eventDispatcher from './h5p-event-dispatcher';
import xAPIEvent from './h5p-x-api-event';
import H5P from './h5p';

export default function(H5PIntegration, window, document) {
  const h5p = H5P(H5PIntegration, window, document);
  eventDispatcher(h5p, H5PIntegration);
  actionBar(h5p, H5PIntegration);
  xAPI(h5p, H5PIntegration);
  xAPIEvent(h5p, H5PIntegration);
  contentType(h5p, H5PIntegration);
  return h5p;
}
