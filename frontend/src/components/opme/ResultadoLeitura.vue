<template>
  <div id="resultado" ref="caixa" :class="classePiscar">
    <div v-if="r" :class="['resultado-linha', r.classe]" :style="r.estilo">
      <div class="icone">{{ r.icone }}</div>
      <div>
        <div class="titulo">{{ r.titulo }}</div>
        <div class="detalhe">{{ r.detalhe }}</div>
        <div v-for="(a, i) in r.alertas || []" :key="i" class="detalhe"><strong>{{ a }}</strong></div>
      </div>
    </div>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue';

// Linha de resultado de cada leitura (verde/vermelho/amarelo, com um "piscar").
interface Resultado { classe: string; icone: string; titulo: string; detalhe?: string; alertas?: string[]; estilo?: string }
const r = ref<Resultado | null>(null);
const classePiscar = ref('');

async function mostrar(ok: boolean | 'alerta', titulo: string, detalhe = '', alertas: string[] = [], icone?: string) {
  const classe = ok === 'alerta' ? 'alerta' : (ok ? 'ok' : 'falha');
  r.value = { classe, icone: icone ?? (ok === 'alerta' ? '!' : (ok ? '✓' : '✕')), titulo, detalhe, alertas };
  classePiscar.value = '';
  await nextTick();
  classePiscar.value = ok && ok !== 'alerta' ? 'piscar-ok' : (ok === 'alerta' ? 'piscar-ok' : 'piscar-erro');
}

function personalizado(res: Resultado | null) {
  r.value = res;
  classePiscar.value = '';
}

function limpar() {
  r.value = null;
}

defineExpose({ mostrar, personalizado, limpar });
</script>
