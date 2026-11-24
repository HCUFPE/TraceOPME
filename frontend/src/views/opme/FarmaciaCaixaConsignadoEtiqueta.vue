<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Etiqueta da caixa</h1>
        <p>Imprima (Ctrl+P) e cole na tampa. É este código que a sala bipa na devolução.</p>
      </div>
      <div class="acoes">
        <button type="button" class="botao" @click="imprimir">Imprimir</button>
        <a class="botao secundario" :href="`${base}/${d.caixa.id_caixa}`">Voltar</a>
      </div>
    </div>
    <div class="cartao" style="max-width:360px;text-align:center">
      <ImagemApi v-if="d.qr_disponivel" :src="`${base}/${encodeURIComponent(d.caixa.id_caixa)}/qr.png`"
                 :alt="`QR da caixa ${d.caixa.id_caixa}`" style="width:240px;height:auto;margin:0 auto" />
      <p v-else class="aviso erro">A biblioteca de QR Code não está instalada no servidor. Peça à TI para instalar as dependências.</p>
      <p class="mono" style="font-size:1.4rem;font-weight:700;margin:.4rem 0">{{ d.caixa.id_caixa }}</p>
      <p style="margin:0">{{ d.caixa.nome }}</p>
      <p class="suave pequeno" style="margin:.2rem 0 0">Consignado · {{ d.caixa.fornecedor || '' }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import ImagemApi from '../../components/opme/ImagemApi.vue';

import { computed } from 'vue';

const props = defineProps<{ d: any }>();
const base = computed(() => props.d.base || '/farmacia/caixas-consignado');
function imprimir() { window.print(); }
</script>
