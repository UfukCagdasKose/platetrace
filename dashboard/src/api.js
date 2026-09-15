import { onMounted, ref } from 'vue'

export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** Her view'in tekrarladigi fetch/durum iskeletini tek yerde topluyor. */
export function useKaynak(yol) {
  const veri = ref([])
  const durum = ref('yukleniyor') // 'yukleniyor' | 'hata' | 'hazir'

  onMounted(async () => {
    try {
      const res = await fetch(`${API_BASE}${yol}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      veri.value = await res.json()
      durum.value = 'hazir'
    } catch (err) {
      console.error(err)
      durum.value = 'hata'
    }
  })

  return { veri, durum }
}
