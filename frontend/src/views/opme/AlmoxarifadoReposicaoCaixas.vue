<template>
  <!-- v18.11.8: o que saiu das caixas por uso no paciente e ainda não voltou a entrar -->
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Reposição das caixas</h1>
        <p>Material usado nos pacientes que ainda não foi reposto na caixa.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/almoxarifado">Voltar</a></div>
    </div>

    <form method="get" action="/almoxarifado/reposicao-caixas" class="cartao filtros">
      <div class="campo"><label for="de">Usados de</label><input type="date" id="de" name="de" :defaultValue="d.de"></div>
      <div class="campo"><label for="ate">até</label><input type="date" id="ate" name="ate" :defaultValue="d.ate"></div>
      <button class="botao">Filtrar</button>
    </form>

    <div class="cartao">
      <div class="entre"><h2>{{ total }} unidade(s) a repor</h2>
        <span class="pequeno">
          <span class="etiqueta verde">enviar</span> o almoxarifado tem ·
          <span class="etiqueta amarelo">parcial</span> tem só parte ·
          <span class="etiqueta vermelho">fornecedor</span> pedir ao fornecedor</span></div>
      <div v-if="d.linhas.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Caixa</th><th>Onde está</th><th>Material</th><th>AGHU</th><th>Fornecedor</th>
            <th class="num">Usados</th><th class="num">Já repostos</th><th class="num">A repor</th>
            <th class="num" title="Saldo livre do almoxarifado para esta linha (já descontado o que as linhas acima vão usar)">Saldo no almoxarifado</th><th>Ação</th></tr></thead>
          <tbody>
            <tr v-for="(l, n) in d.linhas" :key="n">
              <td class="mono"><strong>{{ l.id_caixa }}</strong><br><span class="pequeno suave">{{ l.nome }}</span></td>
              <td class="pequeno">{{ l.farmacia_rotulo }}</td>
              <td>{{ l.descricao }}</td>
              <td class="mono pequeno">{{ l.aghu || '—' }}</td>
              <td class="pequeno">{{ l.fornecedores || '—' }}</td>
              <td class="num">{{ l.usados }}</td>
              <td class="num">{{ l.repostos }}</td>
              <td class="num"><strong>{{ l.faltam }}</strong></td>
              <td class="num">{{ l.no_almoxarifado }}</td>
              <td>
                <span v-if="l.acao === 'enviar'" class="etiqueta verde">{{ l.local === 'almoxarifado' ? 'repor na caixa' : 'enviar à farmácia' }}</span>
                <span v-else-if="l.acao === 'enviar_parcial'" class="etiqueta amarelo">enviar {{ l.no_almoxarifado }} · pedir {{ l.faltam - l.no_almoxarifado }}</span>
                <span v-else class="etiqueta vermelho">pedir ao fornecedor</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nada a repor neste período.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{ d: any }>();
const total = computed(() => (props.d.linhas || []).reduce((s: number, l: any) => s + l.faltam, 0));
</script>
