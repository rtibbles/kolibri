import iFrameView from 'epubjs/src/managers/views/iframe';
import { EVENTS } from 'epubjs/src/utils/constants';
import logger from 'kolibri.lib.logging';
import Contents from './SandboxContents';

const logging = logger.getLogger(__filename);

const $CANONICAL_LINK = null;

function setCanonicalLink() {
  var link = document.querySelector("link[rel='canonical']");
  if (link) {
    link.setAttribute('href', $CANONICAL_LINK);
  } else {
    link = document.createElement('link');
    link.setAttribute('rel', 'canonical');
    link.setAttribute('href', $CANONICAL_LINK);
    document.querySelector('head').appendChild(link);
  }
}

class SandboxIFrameView extends iFrameView {
  registerHandler(handler) {
    const key = new Date().getTime();
    handler = handler.bind(this);
    this.__messageHandlers[key] = handler;
    return key;
  }
  removeHandler(key) {
    try {
      delete this.__messageHandlers[key];
    } catch (e) {
      logging.warn('Error occurred while trying to remove a message handler');
    }
  }
  receiveMessage(event) {
    Object.values(this.__messageHandlers).forEach(handler => handler(event.data));
  }
  sendCommand(code) {
    return this.iframe.contentWindow.postMessage({ eval: code }, '*');
  }
  create() {
    const iframe = super.create();
    this.__messageHandlers = {};
    window.addEventListener('message', this.receiveMessage.bind(this));
    iframe.sandbox = 'allow-scripts';
    this.preamble = `
    <script>
      window.addEventListener("message", receiveMessage, false);

      function receiveMessage(event) {
        if (event.data.eval) {
          (0, eval)(event.data.eval);
        }
      }
    </script>`;
    const bodyProxy = {};

    this.documentProxy = {
      setCanonicalLink() {
        const baseFn = setCanonicalLink.toString();
        const fn = baseFn.replace('$CANONICAL_LINK', this.section.canonical);
        this.sendCommand(fn);
      },
      body: bodyProxy,
    };
    return iframe;
  }

  load(contents) {
    contents = contents.replace('</html>', this.preamble + '</html>');
    return super.load(contents);
  }
  onLoad(event, promise) {
    this.window = this.iframe.contentWindow;
    this.document = this.documentProxy;

    this.contents = new Contents(
      this.document,
      this.document.body,
      this.section.cfiBase,
      this.section.index,
      this
    );

    this.rendering = false;

    this.setCanonicalLink();

    this.contents.on(EVENTS.CONTENTS.EXPAND, () => {
      if (this.displayed && this.iframe) {
        this.expand();
        if (this.contents) {
          this.layout.format(this.contents);
        }
      }
    });

    this.contents.on(EVENTS.CONTENTS.RESIZE, () => {
      if (this.displayed && this.iframe) {
        this.expand();
        if (this.contents) {
          this.layout.format(this.contents);
        }
      }
    });

    promise.resolve(this.contents);
  }
}

export default SandboxIFrameView;
