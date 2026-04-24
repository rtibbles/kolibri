<template>

  <div
    v-if="items.length"
    class="horizontal-card-row"
  >
    <KIconButton
      data-test="scroll-left-button"
      icon="chevronLeft"
      size="small"
      class="scroll-button scroll-left"
      :style="{ backgroundColor: $themeTokens.surface }"
      :disabled="!canScrollLeft"
      @click="scrollLeft"
    />
    <div
      ref="scrollContainer"
      data-test="scroll-container"
      class="scroll-container"
      @scroll="updateScrollState"
    >
      <div
        v-for="(item, idx) in items"
        :key="item.id || idx"
        class="card-slot"
      >
        <slot :item="item" />
      </div>
    </div>
    <KIconButton
      data-test="scroll-right-button"
      icon="chevronRight"
      size="small"
      class="scroll-button scroll-right"
      :style="{ backgroundColor: $themeTokens.surface }"
      :disabled="!canScrollRight"
      @click="scrollRight"
    />
  </div>

</template>


<script>

  export default {
    name: 'HorizontalCardRow',
    props: {
      items: {
        type: Array,
        default: () => [],
      },
    },
    data() {
      return {
        canScrollLeft: false,
        canScrollRight: false,
      };
    },
    mounted() {
      this.updateScrollState();
    },
    methods: {
      updateScrollState() {
        const el = this.$refs.scrollContainer;
        if (!el) return;
        this.canScrollLeft = el.scrollLeft > 0;
        this.canScrollRight = el.scrollLeft < el.scrollWidth - el.clientWidth - 1;
      },
      scrollLeft() {
        const el = this.$refs.scrollContainer;
        if (!el) return;
        el.scrollBy({ left: -el.clientWidth * 0.8, behavior: 'smooth' });
      },
      scrollRight() {
        const el = this.$refs.scrollContainer;
        if (!el) return;
        el.scrollBy({ left: el.clientWidth * 0.8, behavior: 'smooth' });
      },
    },
  };

</script>


<style lang="scss" scoped>

  .horizontal-card-row {
    position: relative;
    display: flex;
    align-items: center;
  }

  .scroll-container {
    display: flex;
    gap: 16px;
    overflow-x: auto;
    scroll-snap-type: x mandatory;
    scrollbar-width: none;

    &::-webkit-scrollbar {
      display: none;
    }
  }

  .card-slot {
    flex-shrink: 0;
    scroll-snap-align: start;
  }

  .scroll-button {
    position: absolute;
    z-index: 2;
    border-radius: 50%;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
  }

  .scroll-left {
    inset-inline-start: -16px;
  }

  .scroll-right {
    inset-inline-end: -16px;
  }

</style>
