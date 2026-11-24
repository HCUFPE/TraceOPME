<template>
  <!-- nov/2026: situação de um envio/devolução entre almoxarifado e farmácia. -->
  <span>
    <span v-if="r.status === 'aberta'" class="etiqueta azul">em montagem</span>
    <span v-else-if="r.status === 'enviada'" class="etiqueta amarelo">aguardando {{ quem === 'almoxarifado' ? 'o almoxarifado' : 'a farmácia' }}</span>
    <span v-else-if="r.status === 'cancelada'" class="etiqueta cinza" :title="r.motivo_cancelamento">cancelado por {{ r.cancelada_por }}</span>
    <template v-else>
      <span class="etiqueta verde">conferido por {{ r.conferida_nome }}</span>
      <span v-if="r.nao_recebidos" class="etiqueta vermelho">{{ r.nao_recebidos }} não recebido(s)</span>
    </template>
  </span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ r: any; quem?: 'almoxarifado' | 'farmacia' }>(), { quem: 'farmacia' });
</script>
