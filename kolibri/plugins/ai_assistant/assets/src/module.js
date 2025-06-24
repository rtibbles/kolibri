import KolibriModule from 'kolibri-module';
import Vue from 'vue';
import AiAssistantFloatingWidget from './AiAssistantFloatingWidget';

class AiAssistantModule extends KolibriModule {
  ready() {
    // Mount to a new div element and append to body
    const mountEl = document.createElement('div');
    document.body.appendChild(mountEl);
    this.rootVue = new Vue(
      Object.assign(
        {
          el: mountEl,
        },
        AiAssistantFloatingWidget,
      ),
    );
  }
}

export default new AiAssistantModule();