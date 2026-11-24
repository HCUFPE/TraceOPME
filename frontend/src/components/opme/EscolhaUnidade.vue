<template>
  <!-- v17 — escolha da unidade: Bloco Cirúrgico ou Hemodinâmica. -->
  <div :class="['cartao', 'seletor-unidade', { 'sem-escolha': !unidadeAtual }]">
    <div class="entre" style="flex-wrap:wrap;gap:.8rem">
      <div>
        <template v-if="unidadeAtual">
          <span class="suave pequeno">Você está em</span><br>
          <strong class="seletor-unidade-atual">{{ unidades[unidadeAtual]?.rotulo }}</strong>
        </template>
        <template v-else>
          <strong class="seletor-unidade-atual">{{ pergunta || 'Onde é o procedimento?' }}</strong><br>
          <span class="suave pequeno">Escolha a unidade antes de começar.</span>
        </template>
      </div>
      <form method="post" :action="acao || '/sala-procedimento/unidade'" class="linha-botoes" style="margin:0">
        <input type="hidden" name="proximo" :value="route.path">
        <button v-for="(dados, chave) in unidades" :key="chave" name="unidade" :value="chave"
                :class="['botao', 'botao-unidade', chave === unidadeAtual ? '' : 'secundario']">
          {{ dados.rotulo }}</button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router';

defineProps<{ unidadeAtual: string; unidades: Record<string, any>; acao?: string; pergunta?: string }>();
const route = useRoute();
</script>
