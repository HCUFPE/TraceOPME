<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Empenhos</h1>
        <p>Saldo por fornecedor e material consignado.</p>
      </div>
      <div class="acoes">
        <a class="botao" href="/consignados/empenhos/novo">Cadastrar empenho</a>
        <a class="botao secundario" href="/consignados"> Voltar</a>
      </div>
    </div>

    <form method="get" action="/consignados/empenhos" class="cartao">
      <div class="filtros">
        <div class="campo"><label>Fornecedor</label><input type="text" name="fornecedor" :defaultValue="d.fornecedor"></div>
        <div class="campo">
          <label>Situação</label>
          <select name="status">
            <option value="" :selected="!d.status">todos</option>
            <option value="ativo" :selected="d.status === 'ativo'">ativos</option>
            <option value="encerrado" :selected="d.status === 'encerrado'">encerrados</option>
          </select>
        </div>
        <div class="campo"><label>Cód. consignado, AGHU, material ou número</label><input type="text" name="termo" :defaultValue="d.termo"></div>
        <button class="botao">Filtrar</button>
      </div>
    </form>

    <div class="cartao">
      <div v-if="d.empenhos?.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Nº</th><th>Fornecedor</th><th>Cód. consignado → AGHU</th><th>Material</th><th>Vigência</th>
                     <th class="num">Saldo</th><th class="num">Valor do saldo</th>
                     <th>Situação</th><th></th></tr></thead>
          <tbody>
            <tr v-for="e in d.empenhos" :key="e.id_empenho">
              <td class="mono">{{ e.identificacao || e.numero }}</td>
              <td>{{ e.fornecedor }}</td>
              <td><CodigosEmpenho :e="e" /></td>
              <td>{{ e.material }}
                <template v-if="e.no_limite"><br><span class="etiqueta vermelho pequeno">{{ e.saldo === 0 ? 'SEM SALDO' : 'limite de segurança — pedir mais empenho' }}</span></template></td>
              <td class="pequeno">
                <template v-if="e.vigencia_inicio || e.vigencia_fim">{{ f.dataBr(e.vigencia_inicio) || '…' }} a {{ f.dataBr(e.vigencia_fim) || '…' }}</template>
                <template v-else>{{ f.dataBr(e.data_empenho) || '—' }}</template>
                <template v-if="e.vigencia === 'vencida'"><br><span class="etiqueta vermelho">vigência vencida</span></template>
                <template v-else-if="e.vigencia === 'futura'"><br><span class="etiqueta cinza">ainda não vigente</span></template>
                <template v-if="e.numero_pregao || e.numero_registro"><br><span class="suave"><template v-if="e.numero_pregao">Pregão {{ e.numero_pregao }}</template><template v-if="e.numero_registro"> · Reg. {{ e.numero_registro }}</template></span></template>
              </td>
              <td class="num">
                <div class="barra-trilho" style="min-width:100px">
                  <div :class="['barra-preenchida', e.no_limite ? 'vermelho' : (e.percentual_usado >= 60 ? 'amarelo' : 'verde')]"
                       :style="{ width: `${e.percentual_usado}%` }"></div>
                </div>
                <span class="pequeno">{{ e.saldo }} de {{ e.quantidade_total }} · limite {{ e.limite }}</span>
              </td>
              <td class="num">{{ f.moeda(e.valor_saldo) }}</td>
              <td><span :class="['etiqueta', e.status === 'ativo' ? 'verde' : 'cinza']">{{ titulo(e.status) }}</span></td>
              <td><a class="botao pequeno secundario" :href="`/consignados/empenhos/${e.id_empenho}`">Abrir</a></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum empenho encontrado com os filtros atuais.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import CodigosEmpenho from '../../components/opme/CodigosEmpenho.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
const titulo = (s: string) => String(s || '').toLowerCase().replace(/(^|\s)\S/g, (c) => c.toUpperCase());
</script>
