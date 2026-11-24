<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Itens utilizados</h1>
        <p>Base para faturamento, prestação de contas e reposição.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/consultas">Voltar</a></div>
    </div>

    <form method="get" action="/consultas/utilizados" class="cartao">
      <div class="filtros">
        <div class="campo"><label>De</label><input type="date" name="inicio" :defaultValue="d.inicio"></div>
        <div class="campo"><label>Até</label><input type="date" name="fim" :defaultValue="d.fim"></div>
        <div class="campo"><label>Prontuário</label><input type="text" name="prontuario" :defaultValue="fi.prontuario"></div>
        <div class="campo">
          <label>Sala</label>
          <select name="sala">
            <option value="">todas</option>
            <option v-for="s in d.salas" :key="s" :value="s" :selected="fi.sala === s">{{ s }}</option>
          </select>
        </div>
        <div class="campo">
          <label>Especialidade</label>
          <select name="especialidade">
            <option value="">todas</option>
            <option v-for="e in d.especialidades" :key="e" :value="e" :selected="fi.especialidade === e">{{ f.especialidade(e) }}</option>
          </select>
        </div>
        <div class="campo"><label>Produto</label><input type="text" name="produto" :defaultValue="fi.produto"></div>
        <button class="botao">Filtrar</button>
      </div>
    </form>

    <div class="cartao">
      <div class="entre">
        <h2>{{ d.linhas.length }} item(ns) utilizado(s)</h2>
        <a v-if="d.linhas.length" class="botao secundario pequeno" data-baixar :href="urlCsv">Exportar CSV</a>
      </div>
      <div v-if="d.linhas.length" class="tabela-rolagem">
        <table>
          <thead>
            <tr><th>Data</th><th>Prontuário</th><th>Sala</th><th>Especialidade</th>
                <th>Produto</th><th>Lote</th><th>Validade</th><th>Fornecedor</th>
                <th>Classificação</th><th class="num">Valor</th></tr>
          </thead>
          <tbody>
            <tr v-for="l in d.linhas" :key="l.id_unidade">
              <td>{{ f.dataBr(l.data_procedimento) }}</td>
              <td>{{ l.prontuario }}</td>
              <td>{{ l.sala }}</td>
              <td>{{ f.especialidade(l.especialidade) }}</td>
              <td><a :href="`/consultas/item/${l.id_unidade}`">{{ l.xProd }}</a></td>
              <td class="mono">{{ l.nLote || '—' }}</td>
              <td>{{ f.dataBr(l.dVal) || '—' }}</td>
              <td class="pequeno">{{ l.fornecedor || '—' }}</td>
              <td class="pequeno">{{ f.titulo(l.tipo_entrada) }}</td>
              <td class="num">{{ f.moeda(l.vUnCom) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum item utilizado com esses filtros.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const fi = computed(() => props.d.filtros || {});
const urlCsv = computed(() => {
  const p = new URLSearchParams({
    inicio: props.d.inicio || '', fim: props.d.fim || '', prontuario: fi.value.prontuario || '',
    sala: fi.value.sala || '', especialidade: fi.value.especialidade || '', produto: fi.value.produto || '', exportar: '1',
  });
  return `/consultas/utilizados?${p.toString()}`;
});
</script>
