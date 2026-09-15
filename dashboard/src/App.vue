<script setup>
import { shallowRef } from 'vue'
import Anomaliler from './views/Anomaliler.vue'
import Aranan from './views/Aranan.vue'
import Klonlar from './views/Klonlar.vue'
import Konvoylar from './views/Konvoylar.vue'

const SEKMELER = [
  { id: 'konvoylar', etiket: 'Konvoylar', bilesen: Konvoylar },
  { id: 'klonlar', etiket: 'Klonlama', bilesen: Klonlar },
  { id: 'anomaliler', etiket: 'Anomaliler', bilesen: Anomaliler },
  { id: 'aranan', etiket: 'Aranan Eşleşmeleri', bilesen: Aranan },
]

const aktifSekme = shallowRef(SEKMELER[0])
</script>

<template>
  <main>
    <header class="baslik">
      <h1>AGIS Analiz Paneli</h1>
    </header>

    <nav class="sekme-cubugu">
      <button
        v-for="s in SEKMELER"
        :key="s.id"
        type="button"
        class="sekme-dugmesi"
        :class="{ aktif: aktifSekme.id === s.id }"
        @click="aktifSekme = s"
      >
        {{ s.etiket }}
      </button>
    </nav>

    <component :is="aktifSekme.bilesen" />
  </main>
</template>
