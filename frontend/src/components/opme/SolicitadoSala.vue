<template>
  <div>
    <h2>Solicitado até agora</h2>
    <SolicitacaoPainel :sol="sol" modo="sala" :atendimento="atendimento" />
    <details v-if="podeEditar && sol.existe" style="margin-top:.8rem"><summary class="pequeno" style="cursor:pointer">Tirar um item da solicitação</summary>
      <ul class="lista" style="margin:.5rem 0 0 1rem">
        <li v-for="l in sol.linhas" :key="l.id_item" class="pequeno">{{ l.quantidade }}x {{ l.descricao }}<template v-if="l.especificacao"> ({{ l.especificacao }})</template>
          <form method="post" :action="`/sala-procedimento/atendimento/${atendimento.id_atendimento}/solicitacao/remover/${l.id_item}`" style="display:inline">
            <button class="botao secundario pequeno">tirar</button></form></li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import SolicitacaoPainel from './SolicitacaoPainel.vue';

defineProps<{ sol: any; atendimento: any; podeEditar: boolean }>();
</script>
