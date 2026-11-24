<template>
  <form method="get" :action="base" class="cartao">
    <div class="filtros">
      <div class="campo"><label>De</label><input type="date" name="inicio" :defaultValue="inicio"></div>
      <div class="campo"><label>Até</label><input type="date" name="fim" :defaultValue="fim"></div>
      <!-- v18.15: Bloco e Hemodinâmica separados (vazio = as duas juntas) -->
      <div v-if="unidades?.length" class="campo">
        <label>Unidade</label>
        <select name="unidade" style="width:14rem">
          <option value="" :selected="!unidade">Bloco + Hemodinâmica</option>
          <option v-for="u in unidades" :key="u.chave" :value="u.chave" :selected="unidade === u.chave">
            Só {{ u.rotulo }}
          </option>
        </select>
      </div>
      <button class="botao">Aplicar</button>
      <a class="botao secundario" :href="base">Últimos 30 dias</a>
      <a class="botao secundario" data-baixar
         :href="`/indicadores/exportar?inicio=${inicio || ''}&fim=${fim || ''}&unidade=${unidade || ''}`">Exportar CSV</a>
      <button type="button" class="botao secundario" @click="imprimir">Imprimir</button>
    </div>
    <p v-if="unidades?.length" class="pequeno suave" style="margin:.5rem 0 0">
      Mostrando: <strong>{{ unidade ? rotuloAtual : 'Bloco Cirúrgico e Hemodinâmica juntos' }}</strong>.
      Um item entra na unidade quando está na farmácia dela ou vinculado a um procedimento dela.
      O que não tem nem farmácia nem procedimento de uma das duas aparece só na visão conjunta.
    </p>
  </form>
</template>

<script setup lang="ts">
import { computed } from 'vue';
const props = defineProps<{
  base: string; inicio: string; fim: string;
  unidade?: string; unidades?: { chave: string; rotulo: string }[];
}>();
const rotuloAtual = computed(
  () => props.unidades?.find((u) => u.chave === props.unidade)?.rotulo || 'todas as unidades');
function imprimir() { window.print(); }
</script>
