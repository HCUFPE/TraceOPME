<template>
  <div class="abas-indicadores">
    <a :href="`/indicadores?${q}`" :class="{ ativa: atual === 'resumo' }">Resumo</a>
    <a :href="`/indicadores/fluxo?${q}`" :class="{ ativa: atual === 'fluxo' }">Fluxo e gargalos</a>
    <a :href="`/indicadores/desperdicio?${q}`" :class="{ ativa: atual === 'desperdicio' }">Desperdício e validade</a>
    <a :href="`/indicadores/financeiro?${q}`" :class="{ ativa: atual === 'financeiro' }">Financeiro e consumo</a>
    <a :href="`/indicadores/qualidade?${q}`" :class="{ ativa: atual === 'qualidade' }">Qualidade</a>
    <a v-if="auth.podeAcessar('admin')" href="/indicadores/metas" :class="{ ativa: atual === 'metas' }">Metas</a>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useAuthStore } from '../../../stores/auth';

const props = defineProps<{ atual: string; inicio?: string; fim?: string; unidade?: string }>();
const auth = useAuthStore();
const q = computed(
  () => `inicio=${props.inicio || ''}&fim=${props.fim || ''}&unidade=${props.unidade || ''}`);
</script>
