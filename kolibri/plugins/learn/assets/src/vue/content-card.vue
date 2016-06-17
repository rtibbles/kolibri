<template>

  <button v-on:click="fetchFullContent(pk)" href="linkhref">
    <div class="content-card-container">
      <img :src="thumbsrc" class="thumbnail">
      <div class="title">
        {{ title }}
      </div>
    </div>
  </button>

</template>


<script>

  module.exports = {
    props: [
      'title',
      'thumbsrc',
      'linkhref',
      'kind',
      'progress',
      'pk',
    ],
    vuex: {
      actions: require('../actions'),
    },
  };

</script>


<style lang="stylus" scoped>

  @require '~core-theme.styl'

  .content-card
    height: 150px
    width: 200px
    background-color: $core-bg-light
    text-align: center


  .thumbnail
    width: 200px
    height: 120px

  .title
    max-width: 200px

</style>
