<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Corrigir cadastro</h1>
        <p>Toda alteração exige motivo e fica registrada no histórico do item. Aqui também se corrige a
          quantidade e se exclui um item cadastrado por engano.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/almoxarifado">Voltar</a></div>
    </div>

    <form method="get" action="/almoxarifado/correcoes" class="cartao">
      <div class="filtros">
        <div class="campo" style="flex:1">
          <label>Buscar por produto, código de barras, lote, fornecedor ou ID</label>
          <input type="text" name="busca" :defaultValue="d.busca" autofocus placeholder="pode bipar a etiqueta da embalagem">
        </div>
        <button class="botao">Buscar</button>
      </div>
    </form>

    <!-- v18.17: mostra o que foi lido da etiqueta bipada (e avisa quando o lote não bate) -->
    <p v-if="d.etiqueta && (d.etiqueta.gtin || d.etiqueta.lote)" class="pequeno suave" style="margin:-.4rem 0 1rem">
      Etiqueta lida:
      <template v-if="d.etiqueta.gtin">produto <strong class="mono">{{ d.etiqueta.gtin }}</strong></template>
      <template v-if="d.etiqueta.lote"> · lote <strong class="mono">{{ d.etiqueta.lote }}</strong></template>
      <template v-if="d.etiqueta.validade"> · validade {{ f.dataBr(d.etiqueta.validade) }}</template>
      <template v-if="d.etiqueta.serie"> · série <strong class="mono">{{ d.etiqueta.serie }}</strong></template>
    </p>
    <p v-if="d.aviso_etiqueta" class="aviso" style="margin:0 0 1rem">{{ d.aviso_etiqueta }}</p>
    <p v-if="d.busca && !d.itens?.length && !d.grupos?.length" class="vazio">
      Nenhum item ativo encontrado para <strong>{{ d.busca }}</strong>. Tente o lote, o código AGHU ou parte do nome
      do produto — itens já utilizados ou baixados não aparecem aqui.</p>

    <template v-if="d.busca && d.grupos?.length">
      <CorrecaoGrupo v-for="(g, n) in d.grupos" :key="n" :g="g" :busca="d.busca" :tipos="d.tipos" />
      <details class="cartao">
        <summary style="cursor:pointer">
          <strong>Ou corrija uma unidade por vez</strong>
          <span class="suave pequeno"> — para o número de série, ou quando só uma está errada ({{ d.itens.length }} encontrada(s))</span>
        </summary>
        <div style="margin-top:1rem">
          <CorrecaoIndividual :itens="d.itens" :busca="d.busca" :tipos="d.tipos" :ids-em-grupo="idsEmGrupo" />
        </div>
      </details>
    </template>
    <CorrecaoIndividual v-else-if="d.busca" :itens="d.itens" :busca="d.busca" :tipos="d.tipos" :ids-em-grupo="idsEmGrupo" />
  </div>
</template>

<script setup lang="ts">
import { useFormatos } from '../../utils/formatos';
import CorrecaoGrupo from '../../components/opme/CorrecaoGrupo.vue';
import CorrecaoIndividual from '../../components/opme/CorrecaoIndividual.vue';

import { computed } from 'vue';

const props = defineProps<{ d: any }>();
// Unidades que fazem parte de um cadastro de várias: a quantidade se corrige no grupo.
const f = useFormatos();
const idsEmGrupo = computed<string[]>(() => (props.d.grupos || []).flatMap((g: any) => g.ids || []));
</script>
