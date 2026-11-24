<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>{{ item.xProd }}</h1>
        <div v-if="d.descritivo_hc" class="descritivo-hc" style="max-width:60rem;margin-bottom:.5rem">
          <span class="rotulo-hc">HC -</span>{{ d.descritivo_hc }}
        </div>
        <p class="mono pequeno">{{ item.id_unidade }}</p>
        <span :class="['etiqueta', f.corStatus(item.status)]">{{ f.rotuloStatus(item.status) }}</span>
        <span class="suave pequeno"> · {{ f.localStatus(item.status) }}</span>
      </div>
      <div class="acoes"><a class="botao secundario" href="/consultas/itens">Voltar</a></div>
    </div>

    <div v-for="(alerta, n) in d.alertas || []" :key="n" class="aviso alerta">{{ alerta }}</div>

    <div v-if="d.caixa" class="aviso">
      Este item está dentro da caixa
      <strong class="mono">{{ d.caixa.id_caixa }}</strong>
      — {{ d.caixa.nome }} ({{ d.caixa.especialidade }}, {{ d.caixa.total }} item(ns)).
      Ele se move junto com ela: só é bipado sozinho no registro de uso.
    </div>

    <div v-if="d.caixas_anteriores?.length" class="cartao">
      <h2>Caixas por onde passou</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Caixa</th><th>Entrou</th><th>Saiu</th><th>Motivo da saída</th></tr></thead>
          <tbody>
            <tr v-for="(c, n) in d.caixas_anteriores" :key="n">
              <td><span class="mono">{{ c.id_caixa }}</span>
                  <span class="suave pequeno"> {{ c.nome }}</span></td>
              <td class="pequeno">{{ f.dataHoraBr(c.entrou_em) }}</td>
              <td class="pequeno">{{ f.dataHoraBr(c.saiu_em) || '— ainda dentro' }}</td>
              <td class="pequeno suave">{{ c.motivo_saida || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="grade grade-2">
      <div class="cartao">
        <h2>Identificação</h2>
        <table>
          <tbody>
            <tr><th>Código de barras</th><td><span class="mono">{{ item.codigo_barras }}</span>
              <div v-if="etiquetaGs1" class="pequeno suave" style="margin-top:.2rem">
                É o código do produto (GTIN). Na embalagem ele vem junto com validade, lote e série:
                <span class="mono">{{ etiquetaGs1 }}</span> — pode bipar a etiqueta inteira nas buscas.</div></td></tr>
            <tr><th>Código AGHU</th><td>{{ item.codigo_aghu || '—' }}</td></tr>
            <tr><th>Código master</th><td class="mono">{{ d.codigo_master || '—' }}</td></tr>
            <tr><th>Nº de série</th><td class="mono">{{ item.numero_serie || '—' }}</td></tr>
            <tr><th>Lote</th><td class="mono">{{ item.nLote || '—' }}</td></tr>
            <tr><th>Fabricação</th><td>{{ f.dataBr(item.dFab) || '—' }}</td></tr>
            <tr><th>Validade</th><td>{{ f.dataBr(item.dVal) || '—' }}</td></tr>
            <tr><th>Marca/Fabricante</th><td>{{ item.marca_fabricante || '—' }}</td></tr>
            <tr><th>Fornecedor</th><td>{{ item.fornecedor || '—' }}</td></tr>
          </tbody>
        </table>
      </div>

      <div class="cartao">
        <h2>Origem e destino</h2>
        <table>
          <tbody>
            <tr><th>Entrada</th><td>{{ item.origem === 'xml' ? 'NF-e' : 'Cadastro manual' }}</td></tr>
            <tr><th>Nota fiscal</th><td>{{ item.numero_nf || '—' }}</td></tr>
            <tr><th>Chave da NF</th><td class="mono pequeno">{{ item.chave_nf || '—' }}</td></tr>
            <tr><th>Classificação</th><td>{{ f.titulo(item.tipo_entrada) }}</td></tr>
            <tr v-if="item.tipo_entrada === 'consignado' || item.codigo_consignado"><th>Código consignado</th>
              <td class="mono">{{ item.codigo_consignado || '—' }}</td></tr>
            <tr><th>Valor unitário</th><td>{{ f.moeda(item.vUnCom) }}</td></tr>
            <tr><th>Cadastrado em</th><td>{{ f.dataHoraBr(item.criado_em) }}</td></tr>
            <template v-if="item.prontuario">
              <tr><th>Prontuário</th>
                  <td><a :href="`/consultas/prontuario?numero=${encodeURIComponent(item.prontuario)}`">{{ item.prontuario }}</a></td></tr>
              <tr><th>Sala</th><td>{{ item.sala }}</td></tr>
              <tr><th>Procedimento</th><td>{{ f.dataBr(item.data_procedimento) }}</td></tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <div class="cartao">
      <h2>Histórico completo</h2>
      <p class="suave pequeno">Cada movimento gravado, com usuário e horário. Não é possível apagar.</p>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Quando</th><th>Movimento</th><th>Situação resultante</th><th>Usuário</th><th>Motivo / observação</th></tr></thead>
          <tbody>
            <tr v-for="(e, n) in d.historico" :key="n">
              <td class="pequeno">{{ f.dataHoraBr(e.data_evento) }}</td>
              <td>{{ f.tituloOperacao(e.tipo) || f.capitalizar(e.tipo) }}</td>
              <td><span v-if="e.status_novo" :class="['etiqueta', f.corStatus(e.status_novo)]">{{ f.rotuloStatus(e.status_novo) }}</span></td>
              <td class="pequeno">{{ e.usuario || '—' }}</td>
              <td class="pequeno">{{ e.motivo || '' }}<template v-if="e.observacao"> <span class="suave">{{ e.observacao }}</span></template></td>
            </tr>
            <tr v-if="!d.historico?.length"><td colspan="5" class="vazio">Sem movimentos registrados.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const item = computed(() => props.d.item);
// Etiqueta GS1 que corresponde a este item: (01)GTIN (17)validade (10)lote (21)série.
const etiquetaGs1 = computed(() => {
  const cb = String(item.value?.codigo_barras || '').replace(/\s/g, '');
  if (!/^\d{8,14}$/.test(cb)) return '';
  let t = `(01)${cb.padStart(14, '0')}`;
  const v = String(item.value?.dVal || '').slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) t += `(17)${v.slice(2, 4)}${v.slice(5, 7)}${v.slice(8, 10)}`;
  if (item.value?.nLote) t += `(10)${item.value.nLote}`;
  if (item.value?.numero_serie) t += `(21)${item.value.numero_serie}`;
  return t;
});
</script>
