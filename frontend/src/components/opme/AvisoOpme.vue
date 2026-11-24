<template>
  <!-- Janela vermelha de bloqueio (aviso tipo "janela") -->
  <div v-if="aviso && aviso.tipo === 'janela'" class="alerta-entrega alerta-janela" role="alertdialog"
       aria-modal="true" aria-labelledby="aviso-janela-titulo">
    <div class="alerta-entrega-janela">
      <div class="alerta-entrega-icone">!</div>
      <h2 id="aviso-janela-titulo">Não é possível concluir</h2>
      <p style="font-size:1.1rem">{{ aviso.texto }}</p>
      <div style="display:flex;gap:.6rem;justify-content:center;flex-wrap:wrap;margin-top:1rem">
        <a v-for="([rotulo, link], i) in aviso.acoes || []" :key="i" class="botao" :href="link"
           data-sem-foco="1" @click.prevent="ir(link)">{{ rotulo }}</a>
        <button type="button" class="botao secundario" data-sem-foco="1" @click="avisos.fechar()">Entendi</button>
      </div>
    </div>
  </div>
  <!-- Faixa de mensagem (sucesso / erro / alerta / info) -->
  <div v-else-if="aviso" :class="['aviso', aviso.tipo]" role="status">
    <div class="entre" style="flex-wrap:nowrap;align-items:flex-start">
      <span>{{ aviso.texto }}</span>
      <button type="button" class="nao-imprimir" style="background:none;border:0;cursor:pointer;font-size:1.1rem;line-height:1;opacity:.6"
              title="Fechar" data-sem-foco="1" @click="avisos.fechar()">×</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAvisoStore } from '../../stores/aviso';

const avisos = useAvisoStore();
const router = useRouter();
const aviso = computed(() => avisos.atual);

function ir(link: string) {
  avisos.fechar();
  router.push(link).catch(() => undefined);
}
</script>
