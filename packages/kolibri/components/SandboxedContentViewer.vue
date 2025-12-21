<template>

  <CoreFullscreen
    ref="fullscreenRef"
    class="sandboxed-content-viewer"
    @changeFullscreen="isFullscreen = $event"
  >
    <div
      class="fullscreen-header"
      :style="{ backgroundColor: $themePalette.grey.v_200 }"
    >
      <KButton
        :primary="false"
        appearance="flat-button"
        @click="toggleFullscreen"
      >
        <KIcon
          :icon="isFullscreen ? 'fullscreen_exit' : 'fullscreen'"
          class="fs-icon"
        />
        {{ fullscreenText }}
      </KButton>
    </div>

    <div
      class="iframe-container"
      :style="containerStyle"
    >
      <iframe
        ref="iframeElement"
        class="iframe"
        sandbox="allow-scripts allow-same-origin"
        :style="{ backgroundColor: $themePalette.grey.v_200 }"
        frameBorder="0"
        :src="sandboxUrl"
        allow="fullscreen"
      >
      </iframe>

      <KCircularLoader
        v-if="loading"
        :delay="false"
        class="loader"
      />
    </div>
  </CoreFullscreen>

</template>


<script>

  import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
  import CoreFullscreen from 'kolibri-common/components/CoreFullscreen';
  import useSandboxedContentViewer, {
    contentViewerProps,
  } from 'kolibri/composables/useSandboxedContentViewer';

  const FRAME_TOPBAR_HEIGHT = '37px';

  export default {
    name: 'SandboxedContentViewer',

    components: {
      CoreFullscreen,
    },

    props: contentViewerProps,

    emits: [
      'startTracking',
      'stopTracking',
      'updateProgress',
      'updateContentState',
      'error',
      'resize',
      'navigateTo',
      'finished',
    ],

    setup(props, context) {
      const viewer = useSandboxedContentViewer(props, context);
      const fullscreenRef = ref(null);
      const iframeElement = ref(null);
      const isFullscreen = ref(false);

      const fullscreenText = computed(() => {
        // Note: These strings should come from $tr in the actual component
        // For now, using English defaults
        return isFullscreen.value ? 'Exit fullscreen' : 'Enter fullscreen';
      });

      const containerStyle = computed(() => {
        if (isFullscreen.value) {
          return {
            position: 'absolute',
            top: FRAME_TOPBAR_HEIGHT,
            bottom: 0,
          };
        }
        return {};
      });

      function toggleFullscreen() {
        fullscreenRef.value?.toggleFullscreen();
      }

      onMounted(async () => {
        // Set the iframe ref on the composable
        viewer.iframeRef.value = iframeElement.value;

        // Initialize the sandbox
        await viewer.initializeSandbox();

        // Emit tracking start
        context.emit('startTracking');
      });

      onBeforeUnmount(() => {
        context.emit('stopTracking');
      });

      return {
        // Template refs
        fullscreenRef,
        iframeElement,

        // State
        isFullscreen,
        loading: viewer.loading,
        sandboxUrl: viewer.sandboxUrl,
        fullscreenText,
        containerStyle,

        // Methods
        toggleFullscreen,

        // Expose for parent access
        getProgress: viewer.getProgress,
        sandbox: viewer.sandbox,
      };
    },

    $trs: {
      exitFullscreen: {
        message: 'Exit fullscreen',
        context:
          "Learners can use the Esc key or the 'exit fullscreen' button to close the fullscreen view.",
      },
      enterFullscreen: {
        message: 'Enter fullscreen',
        context: 'Learners can use the full screen button to open content in fullscreen view.',
      },
    },
  };

</script>


<style lang="scss" scoped>

  @import '~kolibri-design-system/lib/styles/definitions';
  $frame-topbar-height: 37px;

  .sandboxed-content-viewer {
    position: relative;
    text-align: center;
  }

  .fullscreen-header {
    text-align: right;
  }

  .fs-icon {
    position: relative;
    top: 8px;
    width: 24px;
    height: 24px;
  }

  .iframe-container {
    @extend %momentum-scroll;

    width: 100%;
    height: calc(100% - #{$frame-topbar-height});
    margin-bottom: -8px;
    overflow: hidden;
  }

  .iframe {
    width: 100%;
    height: 100%;
  }

  .loader {
    position: absolute;
    top: calc(50% - 16px);
    left: calc(50% - 16px);
  }

</style>
