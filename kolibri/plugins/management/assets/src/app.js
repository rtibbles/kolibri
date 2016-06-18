const KolibriModule = require('kolibri_module');
const Vue = require('vue');
const actions = require('./vuex/actions.js');

class ManagementModule extends KolibriModule {
  ready() {
    this.vm = new Vue({
      el: 'body',
      components: {
        'app-root': require('./app-root.vue'),
      },
      store: require('./vuex/store.js').store,
      vuex: {
        actions: {
          fetch: actions.fetch,
        },
      },
    });
    this.vm.fetch();
  }
}

module.exports = new ManagementModule();
