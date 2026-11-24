<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Indicadores</h1>
        <p>Período de {{ f.dataBr(d.inicio) }} a {{ f.dataBr(d.fim) }}. Passe o mouse no “?” de cada
           indicador para ver como ele é calculado.</p>
      </div>
    </div>

    <AbasIndicadores :unidade="d.unidade" atual="resumo" :inicio="d.inicio" :fim="d.fim" />
    <FiltroPeriodo base="/indicadores" :inicio="d.inicio" :fim="d.fim" :unidade="d.unidade" :unidades="d.unidades" />

    <div v-if="d.criticos?.length" class="cartao borda-vermelha">
      <h2>Fora da meta ({{ d.criticos.length }})</h2>
      <p class="suave pequeno">Estes indicadores estão além do limite de atenção configurado.</p>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Indicador</th><th class="num">Valor</th><th class="num">Meta</th>
                     <th>O que costuma estar por trás</th></tr></thead>
          <tbody>
            <tr v-for="(i, n) in d.criticos" :key="n">
              <td><strong>{{ i.indicador.nome }}</strong></td>
              <td class="num"><span class="etiqueta vermelho">{{ i.texto }}</span></td>
              <td class="num">{{ i.meta_texto }}</td>
              <td class="pequeno">{{ i.indicador.por_que }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="d.atencao?.length" class="cartao borda-amarela">
      <h2>Em atenção ({{ d.atencao.length }})</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Indicador</th><th class="num">Valor</th><th class="num">Meta</th></tr></thead>
          <tbody>
            <tr v-for="(i, n) in d.atencao" :key="n">
              <td>{{ i.indicador.nome }}</td>
              <td class="num"><span class="etiqueta amarelo">{{ i.texto }}</span></td>
              <td class="num">{{ i.meta_texto }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <h2>Visão geral</h2>
    <div class="grade-kpi">
      <KpiCartao v-for="(item, n) in d.destaque" :key="n" :item="item" />
    </div>

    <div class="cartao">
      <h2>Consumo nos últimos 12 meses</h2>
      <p class="suave pequeno">Quantidade de OPMEs implantados por mês.</p>
      <LinhaTempo :dados="d.evolucao" campo-valor="utilizados" titulo="Itens utilizados por mês" />
    </div>

    <div v-for="(dados, chave) in d.grupos" :key="chave" class="cartao">
      <div class="entre">
        <div>
          <h2>{{ dados[0] }}</h2>
          <p class="suave pequeno" style="margin:0">{{ dados[1] }}</p>
        </div>
        <a class="botao secundario pequeno" :href="`/indicadores/${chave}?inicio=${d.inicio}&fim=${d.fim}`">Abrir detalhamento</a>
      </div>
      <div class="tabela-rolagem" style="margin-top:.75rem">
        <table>
          <thead><tr><th>Indicador</th><th>Responde a</th><th class="num">Valor</th>
                     <th class="num">Meta</th><th>Situação</th></tr></thead>
          <tbody>
            <tr v-for="(i, n) in d.por_grupo?.[chave] || []" :key="n">
              <td><strong>{{ i.indicador.nome }}</strong></td>
              <td class="pequeno suave">{{ i.indicador.pergunta }}</td>
              <td class="num"><strong>{{ i.texto }}</strong></td>
              <td class="num pequeno">{{ i.meta !== null && i.meta !== undefined ? i.meta_texto : '—' }}</td>
              <td><SituacaoMeta :situacao="i.situacao" vazio="acompanhamento" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import AbasIndicadores from '../../components/opme/indicadores/AbasIndicadores.vue';
import FiltroPeriodo from '../../components/opme/indicadores/FiltroPeriodo.vue';
import KpiCartao from '../../components/opme/indicadores/KpiCartao.vue';
import LinhaTempo from '../../components/opme/indicadores/LinhaTempo.vue';
import SituacaoMeta from '../../components/opme/indicadores/SituacaoMeta.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
