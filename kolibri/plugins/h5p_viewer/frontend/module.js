import ContentViewerModule from 'kolibri-viewer';
import H5PViewerComponent from './views/H5PViewer';

class H5PViewerModule extends ContentViewerModule {
  get viewerComponent() {
    return H5PViewerComponent;
  }
}

const h5pViewerModule = new H5PViewerModule();

export { h5pViewerModule as default };
