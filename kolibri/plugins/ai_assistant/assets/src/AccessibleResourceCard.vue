<template>

  <a :href="to" style="text-decoration: none; color: inherit">
    <KCard
      :to="to"
      :headingLevel="headingLevel"
      :orientation="windowBreakpoint === 0 ? 'vertical' : 'horizontal'"
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
        <div>
          <slot name="belowTitle"></slot>
          <br v-if="contentNode.description" >
          <KTextTruncator
            v-if="contentNode.description"
            class="truncator"
            :text="contentNode.description"
            :maxLines="2"
            style="min-height: 17px; margin-bottom: 8px"
          />
          <MetadataChips :tags="metadataTags" />
          <div
            v-if="!contentNode.description"
            style="min-height: 17px"
          ></div>
        </div>
      </template>
    </KCard>
  </a>

</template>


<script>

  import { toRefs } from 'vue';
  import { validateLinkObject } from 'kolibri/utils/validators';
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
        type: Object,
        required: true,
        validator: validateLinkObject,
      },
      contentNode: {
        type: Object,
        required: true,
      },
      headingLevel: {
        type: Number,
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
