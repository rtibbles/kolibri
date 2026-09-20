<template>

  <Thumbnail
    :thumbnailUrl="thumbnailUrl"
    :rounded="rounded"
  >
    <template #icon>
      <ComposedThumbnail
        :contentNode="contentNode"
        :aspectRatio="DEFAULT_THUMBNAIL_ASPECT_RATIO"
      />
    </template>

    <template #labels>
      <slot name="labels"></slot>
    </template>
  </Thumbnail>

</template>


<script>

  import ComposedThumbnail, {
    DEFAULT_THUMBNAIL_ASPECT_RATIO,
  } from 'kolibri-common/components/ComposedThumbnail';
  import useChannels from 'kolibri-common/composables/useChannels';
  import Thumbnail from './Thumbnail';

  /**
   * A thumbnail for a content node that shows the content node
   * thumbnail image if it's available.
   * When an image is not available, a composed placeholder
   * thumbnail generated from the node's metadata
   * (ComposedThumbnail) will be displayed.
   */
  export default {
    name: 'ContentNodeThumbnail',
    components: {
      ComposedThumbnail,
      Thumbnail,
    },
    setup() {
      const { getChannelThumbnail } = useChannels();
      return {
        getChannelThumbnail,
        DEFAULT_THUMBNAIL_ASPECT_RATIO,
      };
    },
    props: {
      contentNode: {
        type: Object,
        required: true,
      },
      rounded: {
        type: Boolean,
        required: false,
        default: false,
      },
    },
    computed: {
      thumbnailUrl() {
        const thumbnail = this.contentNode.thumbnail;
        if (!thumbnail) {
          const parent = this.contentNode.parent;
          if (!parent) {
            return this.getChannelThumbnail(this.contentNode && this.contentNode.channel_id);
          }
        }
        return thumbnail;
      },
    },
  };

</script>
