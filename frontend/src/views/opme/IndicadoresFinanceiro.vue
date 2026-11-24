<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Financeiro e consumo</h1>
        <p>Quanto foi consumido, por quem e em quê. Período de {{ f.dataBr(d.inicio) }} a {{ f.dataBr(d.fim) }}.</p>
      </div>
    </div>

    <AbasIndicadores :unidade="d.unidade" atual="financeiro" :inicio="d.inicio" :fim="d.fim" />
    <FiltroPeriodo base="/indicadores/financeiro" :inicio="d.inicio" :fim="d.fim" :unidade="d.unidade" :unidades="d.unidades" />

    <div class="grade-kpi">
      <KpiCartao v-for="(item, n) in d.indicadores" :key="n" :item="item" />
    </div>

    <div class="cartao">
      <h2>Valor consumido nos últimos 12 meses</h2>
      <LinhaTempo :dados="d.evolucao" campo-valor="valor" titulo="Valor consumido por mês" formatador="moeda" />
    </div>

    <div class="grade grade-2">
      <div class="cartao">
        <h2>Consumo por especialidade</h2>
        <template v-if="d.por_especialidade?.length">
          <div class="tabela-rolagem">
            <table>
              <thead><tr><th>Especialidade</th><th class="num">Itens</th><th class="num">Cirurgias</th>
                         <th class="num">Valor</th><th class="num">Custo médio</th></tr></thead>
              <tbody>
                <tr v-for="(l, n) in d.por_especialidade" :key="n">
                  <td>{{ f.titulo(l.chave) }}</td>
                  <td class="num">{{ l.quantidade }}</td>
                  <td class="num">{{ l.cirurgias }}</td>
                  <td class="num">{{ f.moeda(l.valor) }}</td>
                  <td class="num">{{ l.cirurgias ? f.moeda(l.valor / l.cirurgias) : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div style="margin-top:1rem"><BarrasIndicador :linhas="d.por_especialidade" campo-rotulo="chave" campo-valor="valor" formatador="moeda" /></div>
        </template>
        <p v-else class="vazio">Nenhum consumo no período.</p>
      </div>

      <div class="cartao">
        <h2>Consumo por sala</h2>
        <div v-if="d.por_sala?.length" class="tabela-rolagem">
          <table>
            <thead><tr><th>Sala</th><th class="num">Itens</th><th class="num">Cirurgias</th>
                       <th class="num">Valor</th></tr></thead>
            <tbody>
              <tr v-for="(l, n) in d.por_sala" :key="n"><td>{{ l.chave }}</td><td class="num">{{ l.quantidade }}</td>
                  <td class="num">{{ l.cirurgias }}</td><td class="num">{{ f.moeda(l.valor) }}</td></tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhum consumo no período.</p>
      </div>
    </div>

    <div class="grade grade-2">
      <div class="cartao">
        <h2>Consumo por fornecedor</h2>
        <BarrasIndicador v-if="d.por_fornecedor?.length" :linhas="d.por_fornecedor" campo-rotulo="chave" campo-valor="valor" formatador="moeda" cor="roxo" />
        <p v-else class="vazio">Nenhum consumo no período.</p>
      </div>

      <div class="cartao">
        <h2>Consumo por classificação</h2>
        <p class="suave pequeno">Consignado, aquisição própria, doação e empréstimo — base para o
           acerto com os fornecedores.</p>
        <div v-if="d.por_tipo?.length" class="tabela-rolagem">
          <table>
            <thead><tr><th>Classificação</th><th class="num">Itens</th><th class="num">Valor</th></tr></thead>
            <tbody>
              <tr v-for="(l, n) in d.por_tipo" :key="n"><td>{{ f.titulo(l.chave) }}</td>
                  <td class="num">{{ l.quantidade }}</td>
                  <td class="num">{{ f.moeda(l.valor) }}</td></tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhum consumo no período.</p>
      </div>
    </div>

    <div class="cartao">
      <h2>Produtos mais consumidos</h2>
      <div v-if="d.por_produto?.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Produto</th><th class="num">Unidades</th><th class="num">Valor</th>
                     <th class="num">Valor unitário médio</th></tr></thead>
          <tbody>
            <tr v-for="(l, n) in d.por_produto" :key="n">
              <td>{{ l.chave }}</td>
              <td class="num">{{ l.quantidade }}</td>
              <td class="num">{{ f.moeda(l.valor) }}</td>
              <td class="num">{{ l.quantidade ? f.moeda(l.valor / l.quantidade) : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum consumo no período.</p>
    </div>

    <div class="cartao">
      <h2>Cobertura de estoque</h2>
      <p class="suave pequeno">
        Com o consumo observado no período, quantos dias o estoque atual ainda dura. Os primeiros da
        lista são os que acabam antes — atenção especial aos que estão zerados com consumo recente.
      </p>
      <div v-if="d.cobertura?.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Produto</th><th class="num">Em estoque</th>
                     <th class="num">Consumido no período</th><th class="num">Cobertura</th></tr></thead>
          <tbody>
            <tr v-for="(c, n) in d.cobertura" :key="n">
              <td>{{ c.xProd }}</td>
              <td class="num">{{ c.disponivel }}</td>
              <td class="num">{{ c.usados }}</td>
              <td class="num">
                <span v-if="c.dias_cobertura === null || c.dias_cobertura === undefined" class="etiqueta cinza">sem consumo</span>
                <span v-else-if="c.dias_cobertura < 15" class="etiqueta vermelho">{{ Math.trunc(c.dias_cobertura) }} dias</span>
                <span v-else-if="c.dias_cobertura < 45" class="etiqueta amarelo">{{ Math.trunc(c.dias_cobertura) }} dias</span>
                <span v-else class="etiqueta verde">{{ Math.trunc(c.dias_cobertura) }} dias</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Sem dados suficientes para calcular cobertura.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import AbasIndicadores from '../../components/opme/indicadores/AbasIndicadores.vue';
import BarrasIndicador from '../../components/opme/indicadores/BarrasIndicador.vue';
import FiltroPeriodo from '../../components/opme/indicadores/FiltroPeriodo.vue';
import KpiCartao from '../../components/opme/indicadores/KpiCartao.vue';
import LinhaTempo from '../../components/opme/indicadores/LinhaTempo.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
