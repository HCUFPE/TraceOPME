<template>
  <!-- v18.11.7: saídas da caixa numa tela própria, separada do conteúdo -->
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Saídas da caixa {{ d.caixa.id_caixa }}</h1>
        <p>{{ d.caixa.nome }}</p>
      </div>
      <div class="acoes"><a class="botao secundario" :href="d.base">Voltar</a></div>
    </div>

    <form method="get" :action="`${d.base}/${d.caixa.id_caixa}/saidas`" class="cartao filtros">
      <div class="campo"><label for="de">De</label><input type="date" id="de" name="de" :defaultValue="d.de"></div>
      <div class="campo"><label for="ate">Até</label><input type="date" id="ate" name="ate" :defaultValue="d.ate"></div>
      <button class="botao">Filtrar</button>
    </form>

    <div class="cartao">
      <h2>{{ d.saidas.length }} saída(s) no período</h2>
      <div v-if="d.saidas.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Produto</th><th>AGHU</th><th>Lote</th><th>Saiu em</th><th>Por</th><th>Motivo</th><th>Prontuário</th><th>Situação</th></tr></thead>
          <tbody>
            <tr v-for="(s, n) in d.saidas" :key="n">
              <td>{{ s.descritivo_hospital || s.xProd }}</td>
              <td class="mono pequeno">{{ s.codigo_aghu || '—' }}</td>
              <td class="mono">{{ s.nLote || '—' }}</td>
              <td class="pequeno">{{ f.dataHoraBr(s.saiu_em) }}</td>
              <td class="pequeno">{{ s.saiu_por || '—' }}</td>
              <td class="pequeno">{{ s.motivo_saida || '—' }}</td>
              <td class="pequeno">{{ s.prontuario ? `${s.prontuario} · sala ${s.sala || '—'}` : '—' }}</td>
              <td><span :class="['etiqueta', f.corStatus(s.status)]">{{ f.rotuloStatus(s.status) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhuma saída neste período.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
