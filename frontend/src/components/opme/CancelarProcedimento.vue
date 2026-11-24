<template>
  <!-- Procedimento cancelado: motivo + devolução direta do material dispensado. -->
  <details class="cartao cancelar-procedimento" id="cancelar" :hidden="oculto && !aberto" :open="aberto"
           style="margin-top:1rem;border-left:5px solid var(--vermelho, #b3261e)">
    <summary style="cursor:pointer"><strong>Procedimento cancelado?</strong>
      <span class="pequeno suave"> — cancelar com motivo<template v-if="dispensados"> e devolver o material à farmácia</template></span></summary>
    <form method="post" :action="acao" style="margin-top:1rem"
          :data-confirmar="`Cancelar este procedimento?${dispensados ? ` Os ${dispensados} item(ns) dispensado(s) voltam direto para o estoque da farmácia.` : ''}`">
      <input v-if="voltar" type="hidden" name="voltar" :value="voltar">
      <div v-if="dispensados" class="aviso info" style="margin-bottom:.8rem">
        A farmácia dispensou <strong>{{ dispensados }} item(ns)</strong> para este paciente.
        Ao cancelar, eles voltam <strong>direto para o estoque da farmácia</strong> (sem paciente) —
        não precisa bipar a devolução. Fica registrado no histórico de cada item, com o motivo.
      </div>
      <div class="grade grade-2">
        <div class="campo"><label class="obrigatorio">Motivo</label>
          <select name="motivo" required data-sem-foco="1">
            <option value="">— escolha —</option>
            <option v-for="m in motivos" :key="m">{{ m }}</option>
          </select></div>
        <div class="campo"><label>Detalhe <span class="opcional">(obrigatório se “Outro”)</span></label>
          <input type="text" name="detalhe" data-sem-foco="1" placeholder="Ex.: paciente com febre na admissão"></div>
      </div>
      <button class="botao perigo" data-sem-foco="1">Cancelar procedimento<template v-if="dispensados"> e devolver o material</template></button>
    </form>
  </details>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRoute } from 'vue-router';

withDefaults(defineProps<{ acao: string; dispensados?: number; voltar?: string; oculto?: boolean; motivos: string[] }>(), {
  dispensados: 0, voltar: '', oculto: false,
});

// Abre sozinho quando a URL termina em #cancelar (links "Procedimento cancelado").
const route = useRoute();
const aberto = ref(route.hash === '#cancelar');
watch(() => route.hash, (h) => { if (h === '#cancelar') aberto.value = true; });
defineExpose({ abrir: () => { aberto.value = true; } });
</script>
