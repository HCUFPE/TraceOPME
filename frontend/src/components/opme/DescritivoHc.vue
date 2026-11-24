<template>
  <!-- Descrição HC pelo código AGHU (planilha de materiais do hospital). Fica ao
       lado da descrição do fornecedor, nunca no lugar dela. Quando o código não
       está na planilha, avisa — é o caso de código digitado errado. -->
  <div v-if="estado === 'achou'" class="descritivo-hc"><span class="rotulo-hc">HC -</span>{{ descritivo }}</div>
  <div v-else-if="estado === 'nao'" class="descritivo-hc nao-encontrado">
    O código AGHU <strong>{{ consultado }}</strong> não está na planilha de materiais do hospital.
    Confira o número — se for um material novo, fora da licitação, pode registrar assim mesmo.
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { getJson } from '../../services/opme';

const props = defineProps<{ codigo: string | null | undefined }>();
const estado = ref<'' | 'achou' | 'nao'>('');
const descritivo = ref('');
const consultado = ref('');
let temporizador: ReturnType<typeof setTimeout> | null = null;

async function consultar(codigo: string) {
  if (!codigo) { estado.value = ''; consultado.value = ''; return; }
  if (codigo === consultado.value) return;
  consultado.value = codigo;
  try {
    const dados = await getJson(`/almoxarifado/api/descritivo/${encodeURIComponent(codigo)}`);
    // O operador pode ter continuado digitando enquanto a resposta vinha.
    if ((props.codigo || '').trim() !== codigo) return;
    descritivo.value = dados.descritivo || '';
    estado.value = dados.descritivo ? 'achou' : 'nao';
  } catch {
    estado.value = '';
    consultado.value = '';
  }
}

watch(() => (props.codigo || '').trim(), (codigo) => {
  if (temporizador) clearTimeout(temporizador);
  temporizador = setTimeout(() => consultar(codigo), 350);
}, { immediate: true });
</script>
