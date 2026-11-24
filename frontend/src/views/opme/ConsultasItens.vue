<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Itens rastreados</h1>
        <p>Cada linha é uma unidade física, com sua situação atual.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/consultas">Voltar</a></div>
    </div>

    <form method="get" action="/consultas/itens" class="cartao">
      <div class="filtros">
        <div class="campo" style="flex:1">
          <label>Buscar</label>
          <input type="text" name="busca" :defaultValue="d.busca"
                 placeholder="produto, código, lote, fornecedor, nº de série ou ID — ou bipe a embalagem" autofocus>
        </div>
        <div class="campo">
          <label>Situação</label>
          <select name="status">
            <option value="">todas as ativas</option>
            <option value="transito" :selected="d.status === 'transito'">em trânsito (qualquer)</option>
            <option v-for="o in d.opcoes" :key="o.codigo" :value="o.codigo" :selected="d.status === o.codigo">
              {{ o.rotulo }} ({{ o.quantidade }})
            </option>
          </select>
        </div>
        <button class="botao">Filtrar</button>
      </div>
    </form>

    <div class="cartao">
      <div v-if="d.lote_nao_encontrado" id="lote-nao-encontrado" class="aviso erro" style="margin-bottom:.8rem">
        <strong>Código de barras não encontrado:</strong> nenhuma unidade cadastrada com o lote
        <span class="mono">{{ d.lote_nao_encontrado }}</span>.
        <template v-if="d.itens.length"> Abaixo estão outras unidades do <strong>mesmo produto</strong>, de outros lotes.</template>
      </div>
      <div class="entre"><h2>{{ d.itens.length }} resultado(s)</h2></div>
      <template v-if="d.itens.length">
        <div class="tabela-rolagem">
          <table>
            <thead>
              <tr><th>Produto</th><th>Lote</th><th>Validade</th><th>Situação</th><th>Onde está</th>
                  <th>Prontuário</th><th>Fornecedor</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="i in d.itens" :key="i.id_unidade">
                <td>{{ i.xProd }}<br><span class="mono pequeno suave">{{ i.codigo_barras }}</span></td>
                <td class="mono">{{ i.nLote || '—' }}</td>
                <td>{{ f.dataBr(i.dVal) || '—' }}</td>
                <td><span :class="['etiqueta', f.corStatus(i.status)]">{{ f.rotuloStatus(i.status) }}</span></td>
                <td class="pequeno">{{ i.local }}</td>
                <td>{{ i.prontuario || '—' }}</td>
                <td class="pequeno">{{ i.fornecedor || '—' }}</td>
                <td><a class="pequeno" :href="`/consultas/item/${i.id_unidade}`">abrir</a></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="suave pequeno" style="margin-top:.75rem">Exibindo no máximo 300 linhas. Refine a busca se precisar.</p>
      </template>
      <p v-else class="vazio">Nenhum item encontrado.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
