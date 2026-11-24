<template>
  <!-- Sem biblioteca de gráficos: as barras são divs com largura percentual. -->
  <div class="barras">
    <div v-for="(linha, n) in linhas" :key="n" class="barra-linha">
      <div class="barra-rotulo" :title="String(linha[campoRotulo] ?? '')">{{ linha[campoRotulo] }}</div>
      <div class="barra-trilho">
        <div :class="['barra-preenchida', cor]" :style="{ width: `${maximo ? (100 * valor(linha)) / maximo : 0}%` }"></div>
      </div>
      <div class="barra-valor">{{ formatar(valor(linha)) }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { moeda } from '../../../utils/formatos';

const props = withDefaults(defineProps<{
  linhas: any[]; campoRotulo: string; campoValor: string; formatador?: string | null; cor?: string;
}>(), { formatador: null, cor: 'azul' });

const valor = (linha: any) => Number(linha?.[props.campoValor]) || 0;
const maximo = computed(() => (props.linhas || []).reduce((m, l) => Math.max(m, valor(l)), 0));
function formatar(v: number) {
  if (props.formatador === 'moeda') return moeda(v);
  if (props.formatador === 'percentual') return `${v.toFixed(1).replace('.', ',')}%`;
  return String(Math.round(v));
}
</script>
