<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Controle de validades</h1>
        <p>Itens ativos em qualquer ponto do fluxo, do mais próximo do vencimento em diante.</p>
      </div>
      <div class="acoes">
        <a class="botao secundario" data-baixar href="/consultas/validades?exportar=1">Exportar CSV</a>
        <a class="botao secundario" href="/consultas"> Voltar</a>
      </div>
    </div>

    <div class="cartao">
      <div v-if="d.linhas?.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Produto</th><th>Lote</th><th>Fornecedor</th><th>Validade</th>
                     <th>Situação</th><th class="num">Quantidade</th></tr></thead>
          <tbody>
            <tr v-for="(l, n) in d.linhas" :key="n">
              <td>{{ l.xProd }}</td>
              <td class="mono">{{ l.nLote || '—' }}</td>
              <td class="pequeno">{{ l.fornecedor || '—' }}</td>
              <td>{{ f.dataBr(l.dVal) }}</td>
              <td>
                <template v-if="l.dias_restantes !== null && l.dias_restantes !== undefined">
                  <span v-if="l.dias_restantes < 0" class="etiqueta vermelho">vencido há {{ -l.dias_restantes }} dia(s)</span>
                  <span v-else-if="l.dias_restantes <= 30" class="etiqueta amarelo">vence em {{ l.dias_restantes }} dia(s)</span>
                  <span v-else class="etiqueta cinza">{{ l.dias_restantes }} dias</span>
                </template>
              </td>
              <td class="num"><strong>{{ l.quantidade }}</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum item com validade cadastrada dentro do período monitorado.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
