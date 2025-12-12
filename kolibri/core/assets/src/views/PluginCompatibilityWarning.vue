<template>
  <div
    class="plugin-compatibility-warning"
    :style="{
      backgroundColor: $themeTokens.surface,
      borderLeft: `4px solid ${$themeTokens.error}`,
      padding: '16px',
      marginBottom: '16px',
    }"
  >
    <div class="warning-header">
      <KIcon
        icon="warning"
        :style="{ fill: $themeTokens.error, marginRight: '8px' }"
      />
      <h3 :style="{ margin: 0, color: $themeTokens.error }">
        {{ $tr('warningTitle') }}
      </h3>
    </div>
    <p :style="{ marginTop: '8px', marginBottom: 0 }">
      {{ $tr('warningMessage', {
        pluginName: pluginName,
        requirement: versionRequirement,
      }) }}
    </p>
  </div>
</template>

<script>

  export default {
    name: 'PluginCompatibilityWarning',
    props: {
      pluginName: {
        type: String,
        required: true,
      },
      versionRequirement: {
        type: String,
        required: true,
      },
    },
    $trs: {
      warningTitle: {
        message: 'Plugin version incompatibility',
        context: 'Title of warning shown when an incompatible plugin throws an error',
      },
      warningMessage: {
        message: 'The plugin "{pluginName}" may not work correctly. It requires Kolibri {requirement}. Consider disabling this plugin or updating it.',
        context: 'Warning shown when an error occurs in a plugin that has a version compatibility mismatch',
      },
    },
  };

</script>

<style lang="scss" scoped>

  .plugin-compatibility-warning {
    border-radius: 4px;
  }

  .warning-header {
    display: flex;
    align-items: center;
  }

</style>
