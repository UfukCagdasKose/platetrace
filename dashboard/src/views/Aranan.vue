<script setup>
import { computed } from 'vue'
import { useKaynak } from '../api.js'
import DurumMesaji from '../components/DurumMesaji.vue'
import Plaka from '../components/Plaka.vue'
import StatKutu from '../components/StatKutu.vue'

const { veri: eslesmeler, durum } = useKaynak('/aranan/eslesmeler')

const toplamPlaka = computed(() => new Set(eslesmeler.value.map((e) => e.aranan_plaka)).size)

// --- tam vs bulanik eslesme: iki kategori -- kategorik renk (cyan/pink),
// watchlist.py'nin mesafe=0 (tam) / mesafe>0 (fuzzy, ör. 8<->B) ayrimi. ---
const eslesmeSayilari = computed(() => {
  let tam = 0
  let bulanik = 0
  for (const e of eslesmeler.value) {
    if (e.mesafe === 0) tam++
    else bulanik++
  }
  return { tam, bulanik }
})
const eslesmeToplam = computed(() => eslesmeSayilari.value.tam + eslesmeSayilari.value.bulanik || 1)

const sirali = computed(() =>
  [...eslesmeler.value].sort((a, b) => new Date(b.zaman) - new Date(a.zaman)),
)
</script>

<template>
  <section v-if="durum === 'hazir'" class="stat-satiri">
    <StatKutu :deger="eslesmeler.length" etiket="Eşleşme" renk="cyan" />
    <StatKutu :deger="toplamPlaka" etiket="Aranan Plaka" renk="pink" />
  </section>

  <DurumMesaji :durum="durum" :bosMi="eslesmeler.length === 0" bosMetin="Şu an aranan araç eşleşmesi yok." />

  <template v-if="durum === 'hazir' && eslesmeler.length > 0">
    <section class="genel-bakis">
      <h2>Eşleşme Türü</h2>
      <div class="yigin-bar">
        <span
          class="yigin-dilim yigin-dilim--cyan"
          :style="{ width: (eslesmeSayilari.tam / eslesmeToplam) * 100 + '%' }"
          :title="`tam eşleşme: ${eslesmeSayilari.tam}`"
        ></span>
        <span
          class="yigin-dilim yigin-dilim--pink"
          :style="{ width: (eslesmeSayilari.bulanik / eslesmeToplam) * 100 + '%' }"
          :title="`bulanık eşleşme: ${eslesmeSayilari.bulanik}`"
        ></span>
      </div>
      <div class="yigin-lejant">
        <span class="lejant-ogesi"><span class="lejant-nokta lejant-nokta--cyan"></span>tam eşleşme ({{ eslesmeSayilari.tam }})</span>
        <span class="lejant-ogesi"><span class="lejant-nokta lejant-nokta--pink"></span>bulanık eşleşme ({{ eslesmeSayilari.bulanik }})</span>
      </div>
    </section>

    <ul class="konvoy-listesi">
      <li v-for="(e, i) in sirali" :key="i" class="konvoy-karti">
        <div class="plakalar">
          <Plaka :metin="e.okunan_plaka" />
          <template v-if="e.okunan_plaka !== e.aranan_plaka">
            <span class="kenar-ok">↔</span>
            <Plaka :metin="e.aranan_plaka" />
          </template>
        </div>
        <ul class="kenarlar">
          <li>
            <span class="kenar-vurgu">{{ e.sebep }}</span>
            <span class="kenar-detay">
              · mesafe {{ e.mesafe }} · nokta {{ e.nokta_id }} · {{ new Date(e.zaman).toLocaleString('tr-TR') }}
            </span>
          </li>
        </ul>
      </li>
    </ul>
  </template>
</template>
