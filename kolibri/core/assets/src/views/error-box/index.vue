<template>

  <div class="error-box-wrapper" :class="{ hidden: isHidden }">
    <button class="close-button" @click="hideErrorbox" :aria-label="$tr('errorButtonLabel')">
      <mat-svg category="navigation" name="close"/>
    </button>
    <h1>{{ $tr('errorHeader') }}</h1>
    <p>{{ $tr('explanation') }}</p>
    <label for="error-box" aria-live="polite">{{ $tr('errorLabel') }}</label><br>
    <div id="error-box" class="error-box">
      {{ error }}
    </div>
  </div>

</template>


<script>

  export default {
    $trNameSpace: 'error',
    $trs: {
      errorHeader: 'Error',
      errorButtonLabel: 'Hide error',
      explanation: `Sorry, something went wrong. Please try refreshing the page`,
      errorLabel: `Error details:`,
    },
    vuex: {
      getters: {
        error: state => state.core.error,
      },
    },
    data: () => ({
      isHidden: false,
    }),
    methods: {
      hideErrorbox() {
        this.isHidden = true;
      },
    },
  };

</script>


<style lang="stylus" scoped>

  @require '~kolibri.styles.definitions'

  .error-box-wrapper
    padding: 10px
    margin-top: 50px
    position: relative
    background-color: $core-bg-error
    border: 1px solid $core-text-error
    color: $core-text-error

  .hidden
    display: none

  .close-button
    position: absolute
    right: 5px
    top: 5px
    border: none

  .error-box
    max-height: 300px
    padding: 5px
    margin-top: 10px
    overflow: auto
    font-family: monospace
    font-size: 10px
    border: 1px solid black
    background-color: white
    color: $core-text-default

</style>
