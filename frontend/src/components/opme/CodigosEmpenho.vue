<template>
  <!-- nov/2026: códigos cobertos pelo empenho — código consignado e o AGHU associado.
       Empenho antigo (só AGHU) mostra o AGHU. -->
  <span class="mono pequeno">
    <template v-if="e.pares?.length">
      <span v-for="(p, n) in e.pares" :key="p.consignado" style="white-space:nowrap">{{ n ? ', ' : '' }}<strong>{{ p.consignado }}</strong>
        <span class="suave"> → AGHU {{ p.aghu || '—' }}</span></span>
    </template>
    <template v-else>{{ (e.codigos_aghu || []).length ? `AGHU ${e.codigos_aghu.join(', ')}` : '—' }}</template>
  </span>
</template>

<script setup lang="ts">
defineProps<{ e: any }>();
</script>
