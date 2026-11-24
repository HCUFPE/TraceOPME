<template>
  <span v-if="situacao === 'verde'" class="etiqueta verde">na meta</span>
  <span v-else-if="situacao === 'amarelo'" class="etiqueta amarelo">atenção</span>
  <span v-else-if="situacao === 'vermelho'" class="etiqueta vermelho">fora da meta</span>
  <span v-else class="etiqueta cinza">{{ vazio }}</span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ situacao?: string | null; vazio?: string }>(), { situacao: null, vazio: '—' });
</script>
