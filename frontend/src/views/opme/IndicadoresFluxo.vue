<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Fluxo e gargalos</h1>
        <p>Onde o processo trava e quanto tempo cada etapa leva, de {{ f.dataBr(d.inicio) }} a {{ f.dataBr(d.fim) }}.</p>
      </div>
    </div>

    <AbasIndicadores :unidade="d.unidade" atual="fluxo" :inicio="d.inicio" :fim="d.fim" />
    <FiltroPeriodo base="/indicadores/fluxo" :inicio="d.inicio" :fim="d.fim" :unidade="d.unidade" :unidades="d.unidades" />

    <div class="grade-kpi">
      <KpiCartao v-for="(item, n) in d.indicadores" :key="n" :item="item" />
    </div>

    <div class="cartao" id="cancelamentos">
      <h2>Cancelamento de procedimentos</h2>
      <p class="suave pequeno">
        Procedimentos previstos com OPME no período que não aconteceram e foram cancelados na Sala
        com motivo. {{ c.cancelados }} de {{ c.previstos }} previstos
        <template v-if="c.taxa !== null && c.taxa !== undefined">— <strong>{{ f.decimal1(c.taxa) }}%</strong></template>.
      </p>
      <template v-if="c.por_motivo?.length">
        <div class="grade grade-2">
          <div>
            <h3>Por motivo</h3>
            <BarrasIndicador :linhas="c.por_motivo" campo-rotulo="motivo" campo-valor="quantidade" cor="vermelho" />
          </div>
          <div>
            <h3>Por unidade e especialidade</h3>
            <div class="tabela-rolagem">
              <table>
                <thead><tr><th>Unidade</th><th>Especialidade</th><th class="num">Previstos</th>
                           <th class="num">Cancelados</th><th class="num">Taxa</th></tr></thead>
                <tbody>
                  <tr v-for="(g, n) in c.por_grupo" :key="n"><td>{{ g.rotulo_unidade }}</td><td>{{ f.especialidade(g.especialidade) }}</td>
                      <td class="num">{{ g.previstos }}</td><td class="num">{{ g.cancelados }}</td>
                      <td class="num">{{ f.decimal1(g.taxa) }}%</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <details style="margin-top:1rem">
          <summary style="cursor:pointer"><strong>Ver os {{ c.lista.length }} cancelamento(s)</strong></summary>
          <div class="tabela-rolagem" style="margin-top:.6rem">
            <table>
              <thead><tr><th>Data</th><th>Local</th><th>Prontuário</th><th>Especialidade</th>
                         <th>Motivo</th><th>Cancelado por</th></tr></thead>
              <tbody>
                <tr v-for="x in c.lista" :key="x.id_atendimento"><td>{{ f.dataBr(x.data_procedimento) }}</td>
                    <td class="pequeno">{{ x.rotulo_unidade }} — sala {{ x.sala }}</td>
                    <td><a :href="`/sala-procedimento/atendimento/${x.id_atendimento}`">{{ x.prontuario }}</a></td>
                    <td>{{ f.especialidade(x.especialidade) }}</td>
                    <td>{{ x.motivo_cancelamento }}<template v-if="x.detalhe_cancelamento"><br><span class="suave pequeno">{{ x.detalhe_cancelamento }}</span></template></td>
                    <td class="pequeno">{{ x.cancelado_por }}<br>{{ f.dataHoraBr(x.cancelado_em) }}</td></tr>
              </tbody>
            </table>
          </div>
        </details>
      </template>
      <p v-else class="vazio">Nenhum procedimento cancelado no período.</p>
    </div>

    <div class="cartao">
      <h2>Tempo de cada etapa</h2>
      <p class="suave pequeno">
        Medido de verdade, a partir dos eventos gravados. A coluna “90% até” mostra o tempo dentro do
        qual 9 em cada 10 itens foram atendidos — é mais útil que a média para achar o gargalo real.
      </p>
      <div class="tabela-rolagem">
        <table>
          <thead>
            <tr><th>Etapa</th><th class="num">Itens</th><th class="num">Média</th>
                <th class="num">Mediana</th><th class="num">90% até</th>
                <th class="num">Pior caso</th><th class="num">Meta</th><th>Situação</th></tr>
          </thead>
          <tbody>
            <tr v-for="(e, n) in d.etapas" :key="n">
              <td>{{ e.etapa }}</td>
              <td class="num">{{ e.quantidade }}</td>
              <td class="num"><strong>{{ temValor(e.media) ? f.decimal1(e.media) : '—' }}</strong>{{ temValor(e.media) ? ' h' : '' }}</td>
              <td class="num">{{ temValor(e.mediana) ? f.decimal1(e.mediana) : '—' }}</td>
              <td class="num">{{ temValor(e.p90) ? f.decimal1(e.p90) : '—' }}</td>
              <td class="num">{{ temValor(e.maximo) ? f.decimal1(e.maximo) : '—' }}</td>
              <td class="num pequeno">{{ temValor(e.meta) ? e.meta : '—' }}</td>
              <td><SituacaoMeta :situacao="e.situacao" /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <template v-if="comMedia.length">
        <h3 style="margin-top:1.25rem">Comparação visual (horas médias)</h3>
        <BarrasIndicador :linhas="comMedia" campo-rotulo="etapa" campo-valor="media" cor="azul" />
      </template>
    </div>

    <div class="grade grade-2">
      <div class="cartao">
        <h2>Fila de trabalho agora</h2>
        <p class="suave pequeno">Itens esperando alguma ação neste momento, por situação.</p>
        <div v-if="d.gargalos?.length" class="tabela-rolagem">
          <table>
            <thead><tr><th>Situação</th><th class="num">Itens</th>
                       <th class="num">Parados há (média)</th><th class="num">Pior caso</th></tr></thead>
            <tbody>
              <tr v-for="(g, n) in d.gargalos" :key="n">
                <td><span :class="['etiqueta', f.corStatus(g.status)]">{{ f.rotuloStatus(g.status) }}</span></td>
                <td class="num"><strong>{{ g.quantidade }}</strong></td>
                <td class="num">{{ g.dias_medio }} dia(s)</td>
                <td class="num"><span v-if="g.pior_caso && g.pior_caso > 2" class="etiqueta vermelho">{{ g.pior_caso }} dia(s)</span>
                  <template v-else>{{ g.pior_caso || 0 }} dia(s)</template></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhum item pendente. Fluxo limpo.</p>
      </div>

      <div class="cartao">
        <h2>Movimentações por usuário</h2>
        <p class="suave pequeno">Serve para dimensionar equipe, não para comparar pessoas.</p>
        <div v-if="d.produtividade?.length" class="tabela-rolagem">
          <table>
            <thead><tr><th>Usuário</th><th class="num">Movimentos</th>
                       <th class="num">Dias ativos</th><th class="num">Média/dia</th></tr></thead>
            <tbody>
              <tr v-for="(p, n) in d.produtividade" :key="n">
                <td class="mono">{{ p.usuario }}</td>
                <td class="num">{{ p.movimentos }}</td>
                <td class="num">{{ p.dias_ativos }}</td>
                <td class="num">{{ p.media_dia }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhuma movimentação no período.</p>
      </div>
    </div>

    <div class="cartao">
      <h2>Itens parados há mais de 2 dias</h2>
      <p class="suave pequeno">Cada linha é uma conferência que ficou para trás.</p>
      <div v-if="d.parados?.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Item</th><th>Situação</th><th>Prontuário</th>
                     <th class="num">Parado há</th><th></th></tr></thead>
          <tbody>
            <tr v-for="p in d.parados" :key="p.id_unidade">
              <td>{{ p.xProd }} <span class="suave pequeno">lote {{ p.nLote || '—' }}</span></td>
              <td><span :class="['etiqueta', f.corStatus(p.status)]">{{ f.rotuloStatus(p.status) }}</span></td>
              <td>{{ p.prontuario || '—' }}</td>
              <td class="num"><span class="etiqueta vermelho">{{ p.dias_parado }} dia(s)</span></td>
              <td><a class="pequeno" :href="`/consultas/item/${p.id_unidade}`">abrir</a></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum item parado. Todas as conferências estão em dia.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import AbasIndicadores from '../../components/opme/indicadores/AbasIndicadores.vue';
import BarrasIndicador from '../../components/opme/indicadores/BarrasIndicador.vue';
import FiltroPeriodo from '../../components/opme/indicadores/FiltroPeriodo.vue';
import KpiCartao from '../../components/opme/indicadores/KpiCartao.vue';
import SituacaoMeta from '../../components/opme/indicadores/SituacaoMeta.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const c = computed(() => props.d.cancelamentos || {});
const comMedia = computed(() => (props.d.etapas || []).filter((e: any) => e.media));
const temValor = (v: unknown) => v !== null && v !== undefined;
</script>
