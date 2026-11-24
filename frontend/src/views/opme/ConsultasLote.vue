<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Rastreio por lote ou código</h1>
        <p>Use em recall: mostra onde está cada unidade, inclusive as já implantadas.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/consultas">Voltar</a></div>
    </div>

    <form method="get" action="/consultas/lote" class="cartao">
      <div class="filtros">
        <div class="campo" style="flex:1">
          <label>Lote, código de barras ou número de série <span class="opcional">(pode bipar a etiqueta da embalagem)</span></label>
          <input type="text" name="termo" :defaultValue="d.termo" autofocus>
        </div>
        <button class="botao">Rastrear</button>
      </div>
    </form>

    <div v-if="d.termo" class="cartao">
      <h2>{{ d.linhas.length }} unidade(s) encontrada(s)</h2>
      <div v-if="d.linhas.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Produto</th><th>Lote</th><th>Validade</th><th>Situação</th>
                     <th>Prontuário</th><th>Sala</th><th>Data</th><th></th></tr></thead>
          <tbody>
            <tr v-for="l in d.linhas" :key="l.id_unidade">
              <td>{{ l.xProd }}</td>
              <td class="mono">{{ l.nLote || '—' }}</td>
              <td>{{ f.dataBr(l.dVal) || '—' }}</td>
              <td><span :class="['etiqueta', f.corStatus(l.status)]">{{ f.rotuloStatus(l.status) }}</span></td>
              <td>{{ l.prontuario || '—' }}</td>
              <td>{{ l.sala || '—' }}</td>
              <td>{{ f.dataBr(l.data_procedimento) || '—' }}</td>
              <td><a class="pequeno" :href="`/consultas/item/${l.id_unidade}`">abrir</a></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nada encontrado para “{{ d.termo }}”.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
