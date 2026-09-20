<template>

  <KCard
    :to="to"
    :headingLevel="headingLevel"
    :orientation="windowBreakpoint === 0 ? 'vertical' : 'horizontal'"
    thumbnailDisplay="large"
    :title="contentNode.title"
    :thumbnailSrc="thumbnailSrc"
    thumbnailAlign="right"
    thumbnailScaleType="contain"
  >
    <template #thumbnailPlaceholder>
      <ComposedThumbnail
        :contentNode="contentNode"
        :aspectRatio="WIDE_THUMBNAIL_ASPECT_RATIO"
      />
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
    <template #footer>
      <div class="default-icon">
        <KIconButton
          v-if="showBookmarkButton"
          :icon="isBookmarked ? 'bookmark' : 'bookmarkEmpty'"
          size="mini"
          :color="$themePalette.grey.v_700"
          :ariaLabel="
            isBookmarked ? coreString('removeFromBookmarks') : coreString('saveToBookmarks')
          "
          :tooltip="
            isBookmarked ? coreString('removeFromBookmarks') : coreString('saveToBookmarks')
          "
          @click.stop="$emit('toggleBookmark', contentNode.id)"
        />
      </div>
    </template>
    <template #select>
      <slot name="select"></slot>
    </template>
  </KCard>

</template>


<script>

  import { toRefs } from 'vue';
  import { validateLinkObject } from 'kolibri/utils/validators';
  import commonCoreStrings from 'kolibri/uiText/commonCoreStrings';
  import MetadataChips from 'kolibri-common/components/MetadataChips';
  import useKResponsiveWindow from 'kolibri-design-system/lib/composables/useKResponsiveWindow';
  import { useCoachMetadataTags } from 'kolibri-common/composables/useCoachMetadataTags';
  import ComposedThumbnail, { WIDE_THUMBNAIL_ASPECT_RATIO } from '../ComposedThumbnail';

  export default {
    name: 'AccessibleResourceCard',
    components: {
      ComposedThumbnail,
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
        WIDE_THUMBNAIL_ASPECT_RATIO,
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
      isBookmarked: {
        type: Boolean,
        default: false,
      },
      showBookmarkButton: {
        type: Boolean,
        default: true,
      },
      headingLevel: {
        type: Number,
        required: true,
      },
      thumbnailSrc: {
        type: String,
        default: null,
      },
    },
  };

</script>


<style lang="scss" scoped>

  /deep/ .k-with-selection-controls {
    justify-content: flex-end !important;
    max-width: 580px;
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
