<template>

  <SandboxedContentViewer
    v-bind="$props"
    v-on="$listeners"
  />

</template>


<script>

  import SandboxedContentViewer from 'kolibri/components/SandboxedContentViewer';
  import { contentViewerProps } from 'kolibri/composables/useSandboxedContentViewer';

  export default {
    name: 'H5PViewer',

    components: {
      SandboxedContentViewer,
    },

    props: contentViewerProps,
  };

</script>
