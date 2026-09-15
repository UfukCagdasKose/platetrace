<script setup>
import { computed } from 'vue'
import { useKaynak } from '../api.js'
import DurumMesaji from '../components/DurumMesaji.vue'
import Plaka from '../components/Plaka.vue'
import StatKutu from '../components/StatKutu.vue'

// cloning.py'deki MAX_PLAUSIBLE_SPEED_KMH ile ayni -- API'nin kendisi
// esigi asan okumalari zaten donuyor, burada sadece referans cizgisi icin.
const ESIK_KMH = 150

const { veri: klonlar, durum } = useKaynak('/klonlar')

const toplamPlaka = computed(() => new Set(klonlar.value.map((f) => f.plaka)).size)
const enYuksekHiz = computed(() =>
  klonlar.value.length === 0 ? '—' : Math.max(...klonlar.value.map((f) => f.required_speed_kmh)).toFixed(0),
)

// --- hiz kiyaslamasi: esigin ne kadar ustunde oldugu -- diverging degil,
// tek yonlu (hepsi esigi asiyor zaten), o yuzden 0'dan baslayan tek renkli
// bar + esik noktasinda referans cizgisi (dataviz skill: "above a
// baseline" isi icin baseline'i gorunur kilmak). ---
const siraliKlonlar = computed(() =>
  [...klonlar.value].sort((a, b) => b.required_speed_kmh - a.required_speed_kmh),
)
const maxOlcek = computed(() =>
  Math.max(ESIK_KMH * 1.15, ...klonlar.value.map((f) => f.required_speed_kmh), 1),
)
const esikYuzde = computed(() => (ESIK_KMH / maxOlcek.value) * 100)
</script>

<template>
  <section v-if="durum === 'hazir'" class="stat-satiri">
    <StatKutu :deger="klonlar.length" etiket="İmkânsız Hız Çifti" renk="pink" />
    <StatKutu :deger="toplamPlaka" etiket="Etkilenen Plaka" renk="cyan" />
    <StatKutu :deger="`${enYuksekHiz}`" etiket="En Yüksek km/h" renk="pink" kucuk />
  </section>

  <DurumMesaji :durum="durum" :bosMi="klonlar.length === 0" bosMetin="Şu an klonlama şüphesi yok." />

  <template v-if="durum === 'hazir' && klonlar.length > 0">
    <section class="genel-bakis">
      <h2>Gereken Hız <span class="genel-bakis-alt">— kırmızı çizgi {{ ESIK_KMH }} km/h eşiği</span></h2>
      <div
        v-for="(f, i) in siraliKlonlar"
        :key="i"
        class="bar-satir"
        :title="`${f.plaka}: ${f.distance_km} km / ${f.seconds.toFixed(0)} sn → ${f.required_speed_kmh} km/h`"
      >
        <span class="bar-etiket">{{ f.plaka }}</span>
        <span class="bar-track bar-track--esikli">
          <span class="bar-esik-cizgi" :style="{ left: esikYuzde + '%' }"></span>
          <span class="bar-dolgu bar-dolgu--pink" :style="{ width: (f.required_speed_kmh / maxOlcek) * 100 + '%' }"></span>
        </span>
        <span class="bar-deger">{{ f.required_speed_kmh.toFixed(0) }}</span>
      </div>
    </section>

    <ul class="konvoy-listesi">
      <li v-for="(f, i) in siraliKlonlar" :key="i" class="konvoy-karti">
        <div class="plakalar">
          <Plaka :metin="f.plaka" />
        </div>
        <ul class="kenarlar">
          <li>
            <span class="kenar-detay">
              nokta {{ f.from_nokta }} ({{ new Date(f.from_zaman).toLocaleString('tr-TR') }})
              → nokta {{ f.to_nokta }} ({{ new Date(f.to_zaman).toLocaleString('tr-TR') }})
            </span>
          </li>
          <li>
            <span class="kenar-detay">
              {{ f.distance_km }} km / {{ f.seconds.toFixed(0) }} sn →
            </span>
            <span class="kenar-vurgu">{{ f.required_speed_kmh }} km/h</span>
          </li>
        </ul>
      </li>
    </ul>
  </template>
</template>
