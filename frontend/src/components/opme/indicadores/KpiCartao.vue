<template>
  <div :class="['kpi', item.situacao]">
    <div class="kpi-topo">
      <span class="kpi-nome">{{ item.indicador.nome }}</span>
      <span class="kpi-ajuda" tabindex="0"
            :title="`${item.indicador.pergunta}\n\nCálculo: ${item.indicador.formula}\n\nPor quê: ${item.indicador.por_que}`">?</span>
    </div>
    <div class="kpi-valor">{{ item.texto }}</div>
    <div v-if="item.meta !== null && item.meta !== undefined" class="kpi-meta">
      meta: {{ item.indicador.direcao === 'maior' ? 'no mínimo' : 'no máximo' }}
      {{ item.meta_texto }}
      <span v-if="item.personalizada" class="etiqueta cinza">ajustada</span>
    </div>
    <div v-else class="kpi-meta">acompanhamento — sem meta definida</div>
    <div class="kpi-pergunta">{{ item.indicador.pergunta }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ item: any }>();
</script>
