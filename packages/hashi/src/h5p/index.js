import jQuery from 'jquery';
import { v4 as uuidv4 } from 'uuid';

export default class H5P {
  constructor(window) {
    this.window = window;
    this.document = window.document;
    this.jQuery = jQuery;
    this.$body = this.jQuery(this.document.body);
    this.$window = this.jQuery(this.window);
    this.canHasFullScreen = false;
    this.copyRightLicenses = {};
    this.externalEventDispatcher = null;
    this.externalEmbed = false;
    this.fullScreenBrowserPrefix = undefined;
    this.fullScreenSupported = false;
    this.instances = [];
    this.isFramed = false;
    this.opened = {};
    this.preventInit = true;
  }

  init() {}

  classFromName(name) {
    return this[name];
  }

  cloneObject(object, recursive = false) {
    if (recursive) {
      return this.jQuery.extend(true, {}, object);
    }
    return this.jQuery.etend({}, object);
  }

  createTitle(rawTitle, maxLength) {
    return rawTitle.slice(0, maxLength);
  }

  createUUID() {
    return uuidv4();
  }

  cssLoaded(path) {
    return Boolean(path);
  }
}
