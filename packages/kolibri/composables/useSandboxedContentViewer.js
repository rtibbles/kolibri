import { ref, watch, computed, onBeforeUnmount } from 'vue';
import Sandbox from 'kolibri-sandbox';
import coreApp from 'kolibri';
import urls from 'kolibri.urls';
import useContentViewer, { contentViewerProps } from './useContentViewer';
import { getFilePreset, getDefaultFile, getRenderableFiles } from '../components/internal/ContentViewer/utils';

/**
 * Composable for sandboxed content viewers.
 *
 * Wraps useContentViewer and adds sandbox lifecycle management.
 * Handles sandbox initialization, event binding, and cleanup.
 *
 * @param {Object} props - Component props (contentViewerProps)
 * @param {Object} context - Vue component context with emit
 * @param {Object} options - Additional options
 * @returns {Object} Composable state and methods
 */
export default function useSandboxedContentViewer(props, context) {
  // Get base content viewer functionality
  const contentViewer = useContentViewer(props, context);

  // Sandbox state
  const iframeRef = ref(null);
  const sandbox = ref(null);
  const loading = ref(true);

  // Computed: URL to the sandbox HTML page
  const sandboxUrl = computed(() => urls.hashi());

  // Computed: Get the sandbox handler URL for the current content preset
  const sandboxHandlerUrl = computed(() => {
    const defaultFile = contentViewer.defaultFile.value;
    if (!defaultFile) {
      return null;
    }
    const preset = getFilePreset(defaultFile, props.preset);
    return coreApp.getSandboxHandlerUrl(preset);
  });

  /**
   * Initialize the sandbox.
   * Should be called after the iframe is mounted.
   *
   * @returns {Promise<void>}
   */
  async function initializeSandbox() {
    if (!iframeRef.value) {
      throw new Error('iframeRef must be set before initializing sandbox');
    }

    const defaultFile = contentViewer.defaultFile.value;
    if (!defaultFile) {
      contentViewer.reportLoadingError('No renderable file found');
      return;
    }

    // Create sandbox instance
    sandbox.value = new Sandbox({
      iframe: iframeRef.value,
      now: Date.now,
    });

    // Bind sandbox events
    sandbox.value.onStateUpdate(data => {
      context.emit('updateContentState', data);
    });

    sandbox.value.on(sandbox.value.events.LOADING, isLoading => {
      loading.value = isLoading;
    });

    sandbox.value.on(sandbox.value.events.ERROR, err => {
      loading.value = false;
      contentViewer.reportError(err);
    });

    sandbox.value.on(sandbox.value.events.RESIZE, height => {
      context.emit('resize', height);
    });

    // Build user data object
    const userData = {
      userId: props.userId,
      userFullName: props.userFullName,
      progress: props.progress,
      complete: props.progress >= 1,
      language: props.lang?.id,
      timeSpent: props.timeSpent,
    };

    // Get handler URL for this content type
    const handlerUrl = sandboxHandlerUrl.value;

    // Initialize sandbox with content
    sandbox.value.initialize(
      props.extraFields?.contentState || {},
      userData,
      defaultFile.storage_url,
      defaultFile.checksum,
      { handlerUrl },
    );
  }

  /**
   * Get progress from the sandbox/handler.
   * @returns {number|null}
   */
  function getProgress() {
    return sandbox.value?.getProgress() ?? null;
  }

  /**
   * Update user data in the sandbox.
   * Call when props change that should be reflected in sandbox.
   */
  function updateUserData() {
    if (!sandbox.value) return;

    sandbox.value.updateData({
      userData: {
        userId: props.userId,
        userFullName: props.userFullName,
        progress: props.progress,
        complete: props.progress >= 1,
        language: props.lang?.id,
        timeSpent: props.timeSpent,
      },
    });
  }

  // Watch for user data changes
  watch(
    () => ({
      userId: props.userId,
      userFullName: props.userFullName,
      progress: props.progress,
      timeSpent: props.timeSpent,
    }),
    () => {
      updateUserData();
    },
  );

  // Cleanup on unmount
  onBeforeUnmount(() => {
    sandbox.value = null;
  });

  return {
    // From useContentViewer
    ...contentViewer,

    // Sandbox-specific
    iframeRef,
    sandbox,
    loading,
    sandboxUrl,
    sandboxHandlerUrl,
    initializeSandbox,
    getProgress,
    updateUserData,
  };
}

// Re-export props for convenience
export { contentViewerProps };
