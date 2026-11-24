<template>
  <img v-if="url" :src="url" :alt="alt" />
  <span v-else-if="falhou" class="pequeno suave">{{ alt }}</span>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { urlImagem } from '../../services/opme';

// Imagem servida por rota protegida (ex.: QR Code). O <img> comum não envia o
// token JWT, então a imagem é buscada pela API e exibida a partir de um blob.
const props = defineProps<{ src: string; alt?: string }>();
const url = ref('');
const falhou = ref(false);

watch(() => props.src, async (src) => {
  if (url.value) URL.revokeObjectURL(url.value);
  url.value = '';
  falhou.value = false;
  try {
    url.value = await urlImagem(src);
  } catch {
    falhou.value = true;
  }
}, { immediate: true });

onBeforeUnmount(() => { if (url.value) URL.revokeObjectURL(url.value); });
</script>
