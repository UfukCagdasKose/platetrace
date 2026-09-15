<script setup>
import { API_BASE } from '../api.js'

defineProps({
  durum: { type: String, required: true }, // 'yukleniyor' | 'hata' | 'hazir'
  bosMetin: { type: String, default: 'Şu an veri yok.' },
  bosMi: { type: Boolean, default: false },
})
</script>

<template>
  <p v-if="durum === 'yukleniyor'" class="durum-metni">Yükleniyor…</p>
  <p v-else-if="durum === 'hata'" class="durum-metni hata">
    API'ye ulaşılamadı ({{ API_BASE }}). Servisin ayakta olduğundan emin ol.
  </p>
  <p v-else-if="bosMi" class="durum-metni">{{ bosMetin }}</p>
</template>
