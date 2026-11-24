<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Qualidade e conformidade</h1>
        <p>Correções de cadastro, seleção manual, material sem cadastro e problemas com material na sala.
           Período de {{ f.dataBr(d.inicio) }} a {{ f.dataBr(d.fim) }}.</p>
      </div>
    </div>

    <AbasIndicadores :unidade="d.unidade" atual="qualidade" :inicio="d.inicio" :fim="d.fim" />
    <FiltroPeriodo base="/indicadores/qualidade" :inicio="d.inicio" :fim="d.fim" :unidade="d.unidade" :unidades="d.unidades" />

    <div class="grade-kpi">
      <KpiCartao v-for="(item, n) in d.indicadores" :key="n" :item="item" />
    </div>

    <div class="grade grade-2">
      <div class="cartao">
        <h2>Divergências por fornecedor</h2>
        <p class="suave pequeno">
          Concentração em um fornecedor costuma indicar problema de embalagem, romaneio ou
          transporte — e é um argumento objetivo na conversa comercial.
        </p>
        <BarrasIndicador v-if="d.fornecedores?.length" :linhas="d.fornecedores" campo-rotulo="fornecedor" campo-valor="divergencias" cor="vermelho" />
        <p v-else class="vazio">Nenhuma divergência registrada no período.</p>
      </div>

      <div class="cartao">
        <h2>Implantes registrados sem conferência na sala</h2>
        <p class="suave pequeno">
          Precisa ser sempre zero. Qualquer linha aqui é um implante cujo caminho até o paciente
          não pode ser comprovado integralmente em auditoria.
        </p>
        <template v-if="d.fora_do_fluxo?.length">
          <div class="aviso erro">
            {{ d.fora_do_fluxo.length }} registro(s) fora do fluxo. Investigar cada um.
          </div>
          <div class="tabela-rolagem">
            <table>
              <thead><tr><th>Item</th><th>Prontuário</th><th>Sala</th><th>Quando</th><th>Usuário</th></tr></thead>
              <tbody>
                <tr v-for="(x, n) in d.fora_do_fluxo" :key="n">
                  <td><a :href="`/consultas/item/${x.id_unidade}`">{{ x.xProd }}</a>
                      <span class="suave pequeno"> lote {{ x.nLote || '—' }}</span></td>
                  <td>{{ x.prontuario || '—' }}</td>
                  <td>{{ x.sala || '—' }}</td>
                  <td class="pequeno">{{ f.dataHoraBr(x.data_evento) }}</td>
                  <td class="pequeno">{{ x.usuario }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
        <p v-else class="aviso sucesso" style="margin:0">
          Nenhum implante fora do fluxo. Todos passaram pela conferência na sala antes do uso.
        </p>
      </div>
    </div>

    <!-- v18.4.7: material com problema registrado na sala (sem alerta: vira indicador). -->
    <div class="cartao" id="problemas-sala">
      <h2>Problemas com material na sala ({{ ps.total || 0 }})</h2>
      <p class="suave pequeno">Material que caiu, veio danificado ou deu defeito, registrado pela sala no uso do paciente.
        Mostra onde estão os maiores problemas: o motivo, o material, o fornecedor e a sala.</p>
      <template v-if="ps.total">
        <div class="grade grade-2">
          <div>
            <h3>Por motivo</h3>
            <BarrasIndicador :linhas="ps.por_motivo" campo-rotulo="motivo" campo-valor="qtd" cor="vermelho" />
          </div>
          <div>
            <h3>Por fornecedor</h3>
            <BarrasIndicador :linhas="ps.por_fornecedor" campo-rotulo="fornecedor" campo-valor="qtd" cor="vermelho" />
          </div>
        </div>
        <h3>Materiais com mais problemas</h3>
        <div class="tabela-rolagem"><table>
          <thead><tr><th>Material</th><th>AGHU</th><th>Marca</th><th>Fornecedor</th><th>Motivos</th><th class="num">Ocorrências</th></tr></thead>
          <tbody>
            <tr v-for="(m, n) in ps.por_material" :key="n">
              <td>{{ m.descricao }}</td><td class="mono pequeno">{{ m.codigo_aghu || '—' }}</td>
              <td class="pequeno">{{ m.marca }}</td><td class="pequeno">{{ m.fornecedor }}</td>
              <td class="pequeno">{{ String(m.motivos || '').split(',').join(' · ') }}</td><td class="num">{{ m.qtd }}</td>
            </tr>
          </tbody>
        </table></div>
        <h3>Por sala</h3>
        <p class="pequeno"><template v-for="(x, n) in ps.por_sala" :key="n">{{ n ? ' · ' : '' }}{{ f.rotuloUnidade(x.unidade) }} sala {{ x.sala }}: <strong>{{ x.qtd }}</strong></template></p>
        <details>
          <summary style="cursor:pointer"><strong>Registros do período</strong></summary>
          <div class="tabela-rolagem"><table>
            <thead><tr><th>Quando</th><th>Material</th><th>Motivo</th><th>Prontuário</th><th>Sala</th><th>Registrado por</th></tr></thead>
            <tbody>
              <tr v-for="(x, n) in ps.ultimos" :key="n">
                <td class="pequeno">{{ f.dataHoraBr(x.data_evento) }}</td>
                <td><a :href="`/consultas/item/${x.id_unidade}`">{{ x.descricao }}</a>
                  <span class="suave pequeno"> AGHU {{ x.codigo_aghu || '—' }} · lote {{ x.nLote || '—' }}</span></td>
                <td class="pequeno">{{ x.motivo }}<template v-if="x.observacao"> — {{ x.observacao }}</template></td>
                <td>{{ x.prontuario || '—' }}</td><td>{{ x.sala || '—' }}</td><td class="pequeno">{{ x.usuario }}</td>
              </tr>
            </tbody>
          </table></div>
        </details>
      </template>
      <p v-else class="vazio">Nenhum problema com material registrado no período.</p>
    </div>

    <div class="cartao">
      <h2>Onde olhar quando um indicador cai</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Indicador</th><th>Primeira coisa a verificar</th></tr></thead>
          <tbody>
            <tr><td>Taxa de divergência subiu</td>
                <td>Veja o gráfico por fornecedor acima e a
                    <a href="/consultas/eventos">auditoria</a> filtrando pelos dias do pico.</td></tr>
            <tr><td>Correções aumentaram</td>
                <td>Sinal de digitação em vez de leitura do código de barras na entrada.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import AbasIndicadores from '../../components/opme/indicadores/AbasIndicadores.vue';
import BarrasIndicador from '../../components/opme/indicadores/BarrasIndicador.vue';
import FiltroPeriodo from '../../components/opme/indicadores/FiltroPeriodo.vue';
import KpiCartao from '../../components/opme/indicadores/KpiCartao.vue';
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const ps = computed(() => props.d.problemas_sala || {});
</script>
