<script setup>
import { computed } from 'vue'
import { useKaynak } from '../api.js'
import DurumMesaji from '../components/DurumMesaji.vue'
import Plaka from '../components/Plaka.vue'
import StatKutu from '../components/StatKutu.vue'

const { veri: anomaliler, durum } = useKaynak('/anomaliler')

const toplamPlaka = computed(() => new Set(anomaliler.value.map((a) => a.plaka)).size)

// --- tur dagilimi: sadece iki kategori (odd_point / odd_hour) --
// kimlikleri ayirt etmek gerektigi icin kategorik renk (cyan/pink),
// buyukluk kiyasi degil. Bir okuma iki turu birden tasiyabilir, o
// yuzden toplam sayaç turler toplamindan az olabilir. ---
const turSayilari = computed(() => {
  let oddPoint = 0
  let oddHour = 0
  for (const a of anomaliler.value) {
    if (a.types.includes('odd_point')) oddPoint++
    if (a.types.includes('odd_hour')) oddHour++
  }
  return { oddPoint, oddHour }
})
const turToplam = computed(() => turSayilari.value.oddPoint + turSayilari.value.oddHour || 1)

function turEtiketi(types) {
  return types
    .map((t) => (t === 'odd_point' ? 'alışılmadık nokta' : 'alışılmadık saat'))
    .join(' + ')
}
</script>

<template>
  <section v-if="durum === 'hazir'" class="stat-satiri">
    <StatKutu :deger="anomaliler.length" etiket="Anomali Okuması" renk="cyan" />
    <StatKutu :deger="toplamPlaka" etiket="Etkilenen Plaka" renk="pink" />
  </section>

  <DurumMesaji :durum="durum" :bosMi="anomaliler.length === 0" bosMetin="Şu an rota/zaman anomalisi yok." />

  <template v-if="durum === 'hazir' && anomaliler.length > 0">
    <section class="genel-bakis">
      <h2>Tür Dağılımı</h2>
      <div class="yigin-bar">
        <span
          class="yigin-dilim yigin-dilim--cyan"
          :style="{ width: (turSayilari.oddPoint / turToplam) * 100 + '%' }"
          :title="`alışılmadık nokta: ${turSayilari.oddPoint}`"
        ></span>
        <span
          class="yigin-dilim yigin-dilim--pink"
          :style="{ width: (turSayilari.oddHour / turToplam) * 100 + '%' }"
          :title="`alışılmadık saat: ${turSayilari.oddHour}`"
        ></span>
      </div>
      <div class="yigin-lejant">
        <span class="lejant-ogesi"><span class="lejant-nokta lejant-nokta--cyan"></span>alışılmadık nokta ({{ turSayilari.oddPoint }})</span>
        <span class="lejant-ogesi"><span class="lejant-nokta lejant-nokta--pink"></span>alışılmadık saat ({{ turSayilari.oddHour }})</span>
      </div>
    </section>

    <ul class="konvoy-listesi">
      <li v-for="(a, i) in anomaliler" :key="i" class="konvoy-karti">
        <div class="plakalar">
          <Plaka :metin="a.plaka" />
        </div>
        <ul class="kenarlar">
          <li>
            <span class="kenar-detay">
              nokta {{ a.nokta_id }} · {{ new Date(a.zaman).toLocaleString('tr-TR') }}
            </span>
          </li>
          <li>
            <span class="kenar-vurgu">{{ turEtiketi(a.types) }}</span>
            <span class="kenar-detay">
              · en yakın saat farkı {{ a.nearest_hour_gap }}sa · geçmiş {{ a.history_days }} gün
            </span>
          </li>
        </ul>
      </li>
    </ul>
  </template>
</template>
