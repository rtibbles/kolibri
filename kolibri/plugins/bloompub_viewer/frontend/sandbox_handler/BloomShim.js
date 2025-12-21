/**
 * Bloom Player shim for progress tracking.
 *
 * This shim handles the BLOOMPAGESREAD event to calculate progress
 * based on pages read in Bloom content.
 */
import { SandboxShim } from 'kolibri-sandbox';
import { events, nameSpace } from 'kolibri-sandbox/base';

export default class BloomShim extends SandboxShim {
  static shimName = 'BloomPlayer';

  constructor(mediator) {
    super(mediator);
    this.data = {};
    this.userData = {};
    this._hasBeenFlaggedAsComplete = false;
    this.__setData = this.__setData.bind(this);
    this.__setUserData = this.__setUserData.bind(this);
    this.__getProgress = this.__getProgress.bind(this);
    this.on(this.events.STATEUPDATE, this.__setData);
    this.on(this.events.USERDATAUPDATE, this.__setUserData);
    this.on(this.events.BLOOMPAGESREAD, this.__getProgress);
  }

  __setData(data = {}) {
    this.data = data;
  }

  __setUserData(userData = {}) {
    this.userData = userData;
  }

  __getProgress(data = {}) {
    let progress = this.userData.progress || 0;
    if (data.totalNumberedPages) {
      progress = (data.audioPages + data.nonAudioPages + data.videoPages) / data.totalNumberedPages;
      if (!this._hasBeenFlaggedAsComplete && progress >= 1) {
        progress = 0.95;
      }
      this._hasBeenFlaggedAsComplete = data.lastNumberedPageRead;
      this.userData.progress = progress;
    }
    this.__mediator.sendMessage({
      nameSpace: nameSpace,
      event: events.USERDATAUPDATE,
      data: this.userData,
    });
  }

  getProgress() {
    return this.userData.progress || null;
  }

  iframeInitialize(contentWindow) {
    // Bloom Player doesn't need special window patching like H5P
    // The BloomRunner handles setting up the player
  }
}
