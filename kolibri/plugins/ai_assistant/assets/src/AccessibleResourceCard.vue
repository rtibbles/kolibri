<template>

  <a :href="to" style="text-decoration: none; color: inherit; width: 100%;">
    <KCard
      :orientation="windowBreakpoint === 0 ? 'vertical' : 'horizontal'"
      :headingLevel="6"
      thumbnailDisplay="small"
      :title="contentNode.title"
      :thumbnailSrc="contentNode.thumbnail"
      thumbnailAlign="left"
      thumbnailScaleType="contain"
    >
      <template #thumbnailPlaceholder>
        <div class="default-resource-icon">
          <LearningActivityIcon :kind="contentNode.learning_activities" />
        </div>
      </template>
      <template #belowTitle>
        <MetadataChips :tags="metadataTags" />
      </template>
    </KCard>
  </a>

</template>


<script>

  import { toRefs } from 'vue';
  import commonCoreStrings from 'kolibri/uiText/commonCoreStrings';
  import MetadataChips from 'kolibri-common/components/MetadataChips';
  import useKResponsiveWindow from 'kolibri-design-system/lib/composables/useKResponsiveWindow';
  import { useCoachMetadataTags } from 'kolibri-common/composables/useCoachMetadataTags';
  import LearningActivityIcon from 'kolibri-common/components/ResourceDisplayAndSearch/LearningActivityIcon.vue';

  export default {
    name: 'AccessibleResourceCard',
    components: {
      LearningActivityIcon,
      MetadataChips,
    },
    mixins: [commonCoreStrings],
    setup(props) {
      const { contentNode } = toRefs(props);
      const { getResourceTags } = useCoachMetadataTags(contentNode.value);
      const { windowBreakpoint } = useKResponsiveWindow();
      return {
        metadataTags: getResourceTags(),
        windowBreakpoint,
      };
    },
    props: {
      to: {
        type: String,
        required: true,
      },
      contentNode: {
        type: Object,
        required: true,
      },
    },
  };

</script>


<style lang="scss" scoped>

  /deep/ .k-with-selection-controls {
    justify-content: flex-end !important;
    max-width: 580px;
  }

  .default-resource-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    max-height: 160px;
    font-size: 48px;
  }

  .default-icon {
    text-align: right;

    .button {
      width: 32px !important;
      height: 32px !important;
      line-height: 0px;
    }
  }

</style>
