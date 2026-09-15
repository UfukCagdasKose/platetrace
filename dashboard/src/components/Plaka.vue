<script setup>
defineProps({ metin: { type: String, required: true } })
</script>

<template>
  <span class="plaka">
    <span class="plaka-tr">TR</span>
    <span class="plaka-no">{{ metin }}</span>
  </span>
</template>
