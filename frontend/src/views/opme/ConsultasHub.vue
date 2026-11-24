<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Consultas e relatórios</h1>
        <p>Últimos 30 dias ({{ f.dataBr(d.inicio) }} a {{ f.dataBr(d.fim) }}).</p>
      </div>
    </div>

    <div class="grade grade-4">
      <div class="cartao"><div class="numero">{{ d.indicadores.cirurgias }}</div><div class="rotulo">atendimentos no período</div></div>
      <div class="cartao"><div class="numero">{{ d.indicadores.utilizados }}</div><div class="rotulo">OPMEs utilizados</div></div>
      <div class="cartao"><div class="numero">{{ f.moeda(d.indicadores.valor) }}</div><div class="rotulo">valor dos itens utilizados</div></div>
      <div class="cartao"><div class="numero">{{ d.indicadores.aproveitamento }}%</div><div class="rotulo">aproveitamento do que foi à sala</div></div>
    </div>

    <div class="grade grade-3" style="margin-top:1.5rem">
      <a class="acao-card cor-azul" href="/consultas/prontuario"><h3>Por prontuário</h3>
        <p class="rotulo">Tudo que foi implantado em um paciente. Traz o descritivo cirúrgico
           pronto para copiar, baixar em TXT ou imprimir em PDF.</p></a>
      <a class="acao-card cor-azul" href="/consultas/lote"><h3>Por lote ou código</h3>
        <p class="rotulo">Onde está cada unidade de um lote específico.</p></a>
      <a class="acao-card cor-amarelo" href="/consultas/recall"><h3>Recall — bloquear lote</h3>
        <p class="rotulo">Impede a movimentação do lote em todas as áreas e lista quem
           já recebeu o material.</p></a>
      <a class="acao-card cor-azul" href="/consultas/classificacao"><h3>Por classificação</h3>
        <p class="rotulo">Consignado, aquisição própria, doação e empréstimo em um período.</p></a>
      <a class="acao-card cor-azul" href="/consultas/utilizados"><h3>Itens utilizados</h3>
        <p class="rotulo">Relatório por período, com exportação em CSV.</p></a>
      <a class="acao-card cor-azul" href="/consultas/itens"><h3>Todos os itens</h3>
        <p class="rotulo">Busque qualquer unidade e veja a situação atual.</p></a>
      <a class="acao-card cor-azul" href="/consultas/validades"><h3>Validades</h3>
        <p class="rotulo">O que vence primeiro, em qualquer ponto do fluxo.</p></a>
      <a class="acao-card cor-azul" href="/consultas/dispensas"><h3>Movimentações de dispensa</h3>
        <p class="rotulo">Almoxarifado → farmácias e farmácias → sala, por período. Exporta planilha e PDF.</p></a>
      <a class="acao-card cor-azul" href="/consultas/eventos"><h3>Histórico de movimentações</h3>
        <p class="rotulo">Uso, devolução, exclusão, estorno por período, sala, prontuário e tipo. Exporta planilha.</p></a>
      <a v-if="auth.podeAcessar('indicadores')" class="acao-card cor-azul" href="/indicadores"><h3>Indicadores</h3>
        <p class="rotulo">Tempos de ciclo, aproveitamento do kit, desperdício, custos e conformidade.</p></a>
    </div>

    <div class="cartao" style="margin-top:1.5rem">
      <h2>Produtos mais utilizados no período</h2>
      <div v-if="d.top?.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Produto</th><th>Fornecedor</th><th class="num">Quantidade</th><th class="num">Valor total</th></tr></thead>
          <tbody>
            <tr v-for="(t, n) in d.top" :key="n">
              <td>{{ t.xProd }}</td><td>{{ t.fornecedor || '—' }}</td>
              <td class="num">{{ t.quantidade }}</td><td class="num">{{ f.moeda(t.valor_total) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum item utilizado no período.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f, auth } = useTela();
</script>
