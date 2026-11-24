<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Desperdício e validade</h1>
        <p>O que está vencido ou prestes a vencer, e o que foi perdido ou baixado.
           Período de {{ f.dataBr(d.inicio) }} a {{ f.dataBr(d.fim) }}.</p>
      </div>
    </div>

    <AbasIndicadores :unidade="d.unidade" atual="desperdicio" :inicio="d.inicio" :fim="d.fim" />
    <FiltroPeriodo base="/indicadores/desperdicio" :inicio="d.inicio" :fim="d.fim" :unidade="d.unidade" :unidades="d.unidades" />

    <div class="grade-kpi">
      <KpiCartao v-for="(item, n) in d.indicadores" :key="n" :item="item" />
    </div>

    <div class="grade grade-2">
      <div class="cartao">
        <h2>Estoque por faixa de validade</h2>
        <p class="suave pequeno">Fotografia de hoje do estoque do almoxarifado.</p>
        <div class="tabela-rolagem">
          <table>
            <thead><tr><th>Faixa</th><th class="num">Unidades</th><th class="num">Valor</th></tr></thead>
            <tbody>
              <tr v-for="(v, n) in d.vencimentos" :key="n" :class="{ 'destaque-vermelho': v.faixa === 'Já vencidos' && v.quantidade }">
                <td>{{ v.faixa }}</td>
                <td class="num"><strong>{{ v.quantidade }}</strong></td>
                <td class="num">{{ f.moeda(v.valor) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div style="margin-top:1rem">
          <BarrasIndicador :linhas="d.vencimentos || []" campo-rotulo="faixa" campo-valor="valor" formatador="moeda" cor="vermelho" />
        </div>
        <a class="botao secundario pequeno" href="/consultas/validades" style="margin-top:.75rem">Ver item a item</a>
      </div>

      <div class="cartao">
        <h2>Baixas e divergências por motivo</h2>
        <p class="suave pequeno">O texto vem do motivo digitado por quem registrou.</p>
        <div v-if="d.baixas?.length" class="tabela-rolagem">
          <table>
            <thead><tr><th>Motivo</th><th class="num">Unidades</th><th class="num">Valor</th></tr></thead>
            <tbody>
              <tr v-for="(b, n) in d.baixas" :key="n">
                <td>{{ b.motivo }}</td>
                <td class="num">{{ b.quantidade }}</td>
                <td class="num">{{ f.moeda(b.valor) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhuma baixa ou divergência no período.</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import AbasIndicadores from '../../components/opme/indicadores/AbasIndicadores.vue';
import BarrasIndicador from '../../components/opme/indicadores/BarrasIndicador.vue';
import FiltroPeriodo from '../../components/opme/indicadores/FiltroPeriodo.vue';
import KpiCartao from '../../components/opme/indicadores/KpiCartao.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
