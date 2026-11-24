<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Devoluções ao fornecedor</h1>
        <p>Cada devolução tem um número e é de um fornecedor. Abra para ver os itens, baixar o romaneio em PDF
           (com as assinaturas do hospital e do fornecedor) ou cancelar.</p>
      </div>
      <div class="acoes">
        <a class="botao" href="/bipagem/devolver_fornecedor">Devolver ao fornecedor (bipar)</a>
        <a class="botao secundario" href="/almoxarifado">Voltar</a>
      </div>
    </div>

    <form method="get" action="/almoxarifado/romaneios-fornecedor" class="cartao filtros">
      <div class="campo"><label for="rom-inicio">De</label>
        <input type="date" id="rom-inicio" name="inicio" :defaultValue="d.inicio"></div>
      <div class="campo"><label for="rom-fim">Até</label>
        <input type="date" id="rom-fim" name="fim" :defaultValue="d.fim"></div>
      <div class="campo"><label for="rom-fornecedor">Fornecedor</label>
        <select id="rom-fornecedor" name="fornecedor">
          <option value="">todos</option>
          <option v-for="fo in d.fornecedores" :key="fo" :value="fo" :selected="fo === d.fornecedor">{{ fo }}</option>
        </select></div>
      <div class="campo"><label for="rom-status">Situação</label>
        <select id="rom-status" name="status">
          <option value="">todas</option>
          <option v-for="(rot, chave) in d.situacoes" :key="chave" :value="chave" :selected="chave === d.status">{{ rot }}</option>
        </select></div>
      <div class="campo" style="align-self:flex-end"><button class="botao secundario">Filtrar</button></div>
    </form>

    <div class="cartao">
      <h2>{{ d.devolucoes.length }} devolução(ões)</h2>
      <div v-if="d.devolucoes.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Nº</th><th>Data</th><th>Fornecedor</th><th class="num">Itens</th><th class="num">Valor</th>
                     <th>Situação</th><th>Por</th><th></th></tr></thead>
          <tbody>
            <tr v-for="dv in d.devolucoes" :key="dv.id_devolucao">
              <td class="mono"><strong>{{ dv.id_devolucao }}</strong>
                <span v-if="dv.legado" class="etiqueta cinza" title="Agrupada automaticamente (antes da v18)">anterior</span></td>
              <td>{{ f.dataHoraBr(dv.criada_em) }}</td>
              <td>{{ dv.fornecedor }}</td>
              <td class="num">{{ dv.qtd_itens }}</td>
              <td class="num">{{ dv.valor_br }}</td>
              <td><span :class="['etiqueta', dv.status === 'finalizada' ? 'verde' : dv.status === 'aberta' ? 'amarelo' : 'vermelho']">{{ dv.rotulo_status }}</span></td>
              <td class="pequeno">{{ dv.criada_por }}</td>
              <td style="white-space:nowrap">
                <a class="botao pequeno" :href="`/almoxarifado/devolucao-fornecedor/${dv.id_devolucao}`">Abrir</a>
                <a v-if="dv.qtd_itens" class="botao pequeno secundario" data-baixar
                   :href="`/almoxarifado/devolucao-fornecedor/${dv.id_devolucao}/pdf`" style="margin-left:.3rem">PDF</a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhuma devolução com esses filtros.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
