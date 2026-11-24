<template>
  <!-- Gráfico de linha em SVG puro, como na v17. -->
  <svg v-if="dados && dados.length > 1" :viewBox="`0 0 ${LARGURA} ${ALTURA + 34}`" class="grafico-linha" role="img" :aria-label="titulo">
    <line v-for="n in 5" :key="'g' + n" x1="0" :y1="(ALTURA * (n - 1)) / 4" :x2="LARGURA" :y2="(ALTURA * (n - 1)) / 4"
          stroke="#e3e7ec" stroke-width="1" />
    <polyline fill="none" stroke="#0f766e" stroke-width="2.5" stroke-linejoin="round" :points="pontos" />
    <template v-for="(d, i) in dados" :key="i">
      <circle :cx="x(i)" :cy="y(d)" r="4" fill="#0f766e" />
      <text :x="x(i)" :y="ALTURA + 16" font-size="11" fill="#5c6470" :text-anchor="ancora(i)">
        {{ String(d.mes).slice(5) }}/{{ String(d.mes).slice(2, 4) }}
      </text>
      <text :x="x(i)" :y="ALTURA + 30" font-size="10" fill="#1c2430" :text-anchor="ancora(i)">
        {{ formatador === 'moeda' ? `${Math.round(v(d) / 1000)} mil` : Math.round(v(d)) }}
      </text>
    </template>
  </svg>
  <p v-else class="vazio">Dados insuficientes para montar a série histórica.</p>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(defineProps<{ dados: any[]; campoValor: string; titulo: string; formatador?: string }>(), {
  formatador: 'numero',
});
const LARGURA = 720;
const ALTURA = 180;
const v = (d: any) => Number(d?.[props.campoValor]) || 0;
const maximo = computed(() => (props.dados || []).reduce((m, d) => Math.max(m, v(d)), 0));
const passo = computed(() => LARGURA / Math.max((props.dados || []).length - 1, 1));
const x = (i: number) => i * passo.value;
const y = (d: any) => ALTURA - (maximo.value ? (ALTURA * v(d)) / maximo.value : 0);
const pontos = computed(() => (props.dados || []).map((d, i) => `${x(i)},${y(d)}`).join(' '));
const ancora = (i: number) => (i === 0 ? 'start' : (i === props.dados.length - 1 ? 'end' : 'middle'));
</script>
