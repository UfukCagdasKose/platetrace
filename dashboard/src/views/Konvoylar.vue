<script setup>
import { computed } from 'vue'
import { useKaynak } from '../api.js'
import DurumMesaji from '../components/DurumMesaji.vue'
import Plaka from '../components/Plaka.vue'
import StatKutu from '../components/StatKutu.vue'

const { veri: konvoylar, durum } = useKaynak('/konvoylar')

// --- ustteki ozet halkalari: hicbir sayi uydurulmuyor, /konvoylar
// cevabinin farkli acilardan ozetlenmesi. ---
const toplamPlaka = computed(
  () => new Set(konvoylar.value.flatMap((k) => k.plakalar)).size,
)
const tumKenarlar = computed(() => konvoylar.value.flatMap((k) => k.kenarlar))
const ortalamaAgirlik = computed(() => {
  const kenarlar = tumKenarlar.value
  if (kenarlar.length === 0) return '—'
  return (kenarlar.reduce((s, e) => s + e.weight, 0) / kenarlar.length).toFixed(3)
})

// --- genel bakis cubugu: adaylari ortalama kenar agirligina gore
// karsilastirir (buyukluk kiyasi -> tek renkli yatay bar, dataviz
// skill'inin "compare magnitude" kurali). ---
const genelBakis = computed(() =>
  konvoylar.value
    .map((k, i) => ({
      orijinalIndex: i,
      plakalar: k.plakalar,
      ortalama: k.kenarlar.reduce((s, e) => s + e.weight, 0) / k.kenarlar.length,
    }))
    .sort((a, b) => b.ortalama - a.ortalama),
)
const maxOrtalama = computed(() =>
  Math.max(...genelBakis.value.map((k) => k.ortalama), 0.0001),
)

// --- her kart icindeki iliski grafi: dugumler plaka, kenar kalinligi
// TUM adaylar arasindaki agirlik araligina gore normalize -- bir kartin
// kendi ici degil, butun veri seti kiyaslaniyor. ---
const agirlikAraligi = computed(() => {
  const w = tumKenarlar.value.map((e) => e.weight)
  if (w.length === 0) return { min: 0, max: 1 }
  return { min: Math.min(...w), max: Math.max(...w) }
})

function cizgiKalinligi(weight) {
  const { min, max } = agirlikAraligi.value
  if (max === min) return 3
  const t = (weight - min) / (max - min)
  return 1.5 + t * 4.5
}

const GRAF_GENISLIK = 360
const GRAF_YUKSEKLIK = 180
function dugumNoktasi(index, toplam) {
  const cx = GRAF_GENISLIK / 2
  const cy = GRAF_YUKSEKLIK / 2
  const rx = GRAF_GENISLIK / 2 - 50
  const ry = GRAF_YUKSEKLIK / 2 - 40
  const aci = -Math.PI / 2 + (index * 2 * Math.PI) / toplam
  return { x: cx + rx * Math.cos(aci), y: cy + ry * Math.sin(aci) }
}
</script>

<template>
  <section v-if="durum === 'hazir'" class="stat-satiri">
    <StatKutu :deger="konvoylar.length" etiket="Konvoy Adayı" renk="cyan" />
    <StatKutu :deger="toplamPlaka" etiket="İlişkili Plaka" renk="pink" />
    <StatKutu :deger="ortalamaAgirlik" etiket="Ort. Ağırlık" renk="cyan" kucuk />
  </section>

  <DurumMesaji :durum="durum" :bosMi="konvoylar.length === 0" bosMetin="Şu an konvoy adayı yok." />

  <template v-if="durum === 'hazir' && konvoylar.length > 0">
    <section class="genel-bakis">
      <h2>Genel Bakış <span class="genel-bakis-alt">— ortalama ağırlığa göre</span></h2>
      <div
        v-for="k in genelBakis"
        :key="k.orijinalIndex"
        class="bar-satir"
        :title="`${k.plakalar.join(', ')} — ort. ağırlık ${k.ortalama.toFixed(3)}`"
      >
        <span class="bar-etiket">K{{ k.orijinalIndex + 1 }}</span>
        <span class="bar-track">
          <span class="bar-dolgu" :style="{ width: (k.ortalama / maxOrtalama) * 100 + '%' }"></span>
        </span>
        <span class="bar-deger">{{ k.ortalama.toFixed(3) }}</span>
      </div>
    </section>

    <ul class="konvoy-listesi">
      <li v-for="(k, i) in konvoylar" :key="i" class="konvoy-karti">
        <h3 class="karti-baslik">K{{ i + 1 }}</h3>

        <div class="konvoy-gorsel" :style="{ aspectRatio: `${GRAF_GENISLIK} / ${GRAF_YUKSEKLIK}` }">
          <svg class="aci-svg" :viewBox="`0 0 ${GRAF_GENISLIK} ${GRAF_YUKSEKLIK}`" preserveAspectRatio="xMidYMid meet">
            <line
              v-for="(e, j) in k.kenarlar"
              :key="j"
              :x1="dugumNoktasi(k.plakalar.indexOf(e.a), k.plakalar.length).x"
              :y1="dugumNoktasi(k.plakalar.indexOf(e.a), k.plakalar.length).y"
              :x2="dugumNoktasi(k.plakalar.indexOf(e.b), k.plakalar.length).x"
              :y2="dugumNoktasi(k.plakalar.indexOf(e.b), k.plakalar.length).y"
              :stroke-width="cizgiKalinligi(e.weight)"
              class="aci-cizgi"
            ><title>{{ e.a }} ↔ {{ e.b }}: ağırlık {{ e.weight.toFixed(3) }}, noktalar {{ e.noktalar.join(', ') }}</title></line>
          </svg>
          <div
            v-for="(p, idx) in k.plakalar"
            :key="p"
            class="aci-dugum"
            :style="{
              left: (dugumNoktasi(idx, k.plakalar.length).x / GRAF_GENISLIK) * 100 + '%',
              top: (dugumNoktasi(idx, k.plakalar.length).y / GRAF_YUKSEKLIK) * 100 + '%',
            }"
          >
            <Plaka :metin="p" />
          </div>
        </div>

        <ul class="kenarlar">
          <li v-for="(e, j) in k.kenarlar" :key="j">
            <span class="kenar-plaka">{{ e.a }}</span>
            <span class="kenar-ok">↔</span>
            <span class="kenar-plaka">{{ e.b }}</span>
            <span class="kenar-detay">ağırlık {{ e.weight.toFixed(3) }} · noktalar {{ e.noktalar.join(', ') }}</span>
          </li>
        </ul>
      </li>
    </ul>
  </template>
</template>
