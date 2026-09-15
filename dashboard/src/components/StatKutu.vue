<script setup>
defineProps({
  deger: { type: [String, Number], required: true },
  etiket: { type: String, required: true },
  renk: { type: String, default: 'cyan' }, // 'cyan' | 'pink'
  kucuk: { type: Boolean, default: false },
})
</script>

<template>
  <div class="stat-kutu" :class="`stat-kutu--${renk}`">
    <div class="stat-halka">
      <span class="stat-sayi" :class="{ 'stat-sayi--kucuk': kucuk }">{{ deger }}</span>
    </div>
    <p class="stat-etiket">{{ etiket }}</p>
  </div>
</template>
