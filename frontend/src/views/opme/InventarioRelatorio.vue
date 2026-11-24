<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Relatório da contagem</h1>
        <p class="mono">{{ inv.id_inventario }} · {{ inv.local_rotulo }}</p>
        <p class="suave pequeno">
          Aberta por {{ inv.criado_por }} em {{ f.dataHoraBr(inv.criado_em) }}.
          <template v-if="inv.encerrado_em">Encerrada por {{ inv.encerrado_por }} em {{ f.dataHoraBr(inv.encerrado_em) }}.</template>
          <template v-else><strong>Ainda em contagem</strong> — este resultado é parcial.</template>
          <template v-if="inv.observacao"><br>{{ inv.observacao }}</template>
        </p>
      </div>
      <div class="acoes">
        <button type="button" class="botao secundario" @click="imprimir">Imprimir</button>
        <a class="botao secundario" data-baixar :href="`/inventario/${inv.id_inventario}/relatorio?exportar=2`"> Exportar consolidado (CSV)</a>
        <a v-if="d.total_pendencias" class="botao secundario" data-baixar :href="`/inventario/${inv.id_inventario}/relatorio?exportar=1`"> Exportar pendências (CSV)</a>
        <a v-if="inv.status === 'aberto'" class="botao" :href="`/inventario/${inv.id_inventario}`"> Continuar contando</a>
        <a class="botao secundario" href="/inventario"> Voltar</a>
      </div>
    </div>

    <div class="grade grade-4" style="margin-bottom:1.5rem">
      <div class="cartao"><div class="rotulo">esperados no local</div>
        <div class="numero">{{ d.resumo.esperados }}</div></div>
      <div class="cartao"><div class="rotulo">conferidos</div>
        <div class="numero">{{ d.resumo.conferidos }}</div></div>
      <div class="cartao"><div class="rotulo">não encontrados</div>
        <div class="numero">{{ d.nao_encontrados.length }}</div></div>
      <div class="cartao"><div class="rotulo">total de pendências</div>
        <div class="numero">{{ d.total_pendencias }}</div></div>
    </div>

    <div v-if="!d.total_pendencias" class="aviso sucesso">
      <strong>O estoque fecha.</strong> Tudo que o sistema esperava em
      {{ inv.local_rotulo }} foi bipado, e nada apareceu fora do lugar.
    </div>

    <div class="cartao" style="margin-bottom:1.5rem">
      <h2>Consolidado por material (código AGHU)</h2>
      <p class="suave pequeno">Para cada material: quanto o sistema esperava em {{ inv.local_rotulo }}, quanto foi
        encontrado na contagem, quanto não foi encontrado e quanto apareceu a mais ou fora do lugar.</p>
      <div v-if="d.consolidado?.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>AGHU</th><th>Material (descrição AGHU)</th><th class="num">Esperado no sistema</th>
                     <th class="num">Encontrado</th><th class="num">Não encontrado</th><th class="num">A mais / fora do lugar</th>
                     <th>Resultado</th></tr></thead>
          <tbody>
            <tr v-for="(l, n) in d.consolidado" :key="n">
              <td class="mono">{{ l.codigo_aghu }}</td>
              <td>{{ l.descricao || '—' }}</td>
              <td class="num">{{ l.esperado }}</td>
              <td class="num">{{ l.encontrado }}</td>
              <td class="num"><strong v-if="l.nao_encontrado" style="color:var(--vermelho)">{{ l.nao_encontrado }}</strong><template v-else>0</template></td>
              <td class="num"><strong v-if="l.a_mais" style="color:var(--amarelo)">{{ l.a_mais }}</strong><template v-else>0</template></td>
              <td><span v-if="l.resultado === 'confere'" class="etiqueta verde">confere</span>
                  <span v-else :class="['etiqueta', l.nao_encontrado ? 'vermelho' : 'amarelo']">{{ l.resultado }}</span></td>
            </tr>
          </tbody>
          <tfoot><tr><th></th><th>Total</th>
            <th class="num">{{ soma('esperado') }}</th>
            <th class="num">{{ soma('encontrado') }}</th>
            <th class="num">{{ soma('nao_encontrado') }}</th>
            <th class="num">{{ soma('a_mais') }}</th><th></th></tr></tfoot>
        </table>
      </div>
      <p v-else class="vazio">Nada esperado neste local e nada bipado.</p>
    </div>

    <div v-if="d.nao_encontrados.length" class="cartao" style="border-left:5px solid var(--vermelho);margin-bottom:1.5rem">
      <h2>{{ d.nao_encontrados.length }} não encontrado(s) na contagem</h2>
      <p class="suave pequeno">
        O sistema esperava estes materiais em {{ inv.local_rotulo }} e eles
        não foram bipados. Procure fisicamente antes de dar baixa: o mais comum é
        estar em outra prateleira, ou já ter sido usado na sala sem ninguém bipar.
      </p>
      <TabelaItens :itens="d.nao_encontrados" />
    </div>

    <template v-for="(itens, chave) in d.grupos" :key="chave">
      <div v-if="itens?.length" class="cartao" style="border-left:5px solid var(--amarelo);margin-bottom:1.5rem">
        <h2>{{ itens.length }} · {{ d.situacoes?.[chave] }}</h2>
        <p class="suave pequeno">{{ d.explicacoes?.[chave] }}</p>
        <TabelaItens :itens="itens" mostrar-codigo-lido />
      </div>
    </template>

    <div class="cartao">
      <h2>{{ (d.conferidos || []).length }} conferido(s)</h2>
      <p class="suave pequeno">
        Material bipado e encontrado exatamente onde o sistema dizia que estava.
        Nada a fazer com estes.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const inv = computed(() => props.d.inventario);
function soma(campo: string) {
  return (props.d.consolidado || []).reduce((s: number, l: any) => s + (Number(l[campo]) || 0), 0);
}
function imprimir() { window.print(); }

/** Tabela de itens (o macro tabela_itens da v17). */
const TabelaItens = defineComponent({
  props: { itens: { type: Array as () => any[], required: true }, mostrarCodigoLido: { type: Boolean, default: false } },
  setup(p) {
    return () => h('div', { class: 'tabela-rolagem' }, [
      h('table', { class: 'tabela-detalhe' }, [
        h('thead', [h('tr', [
          ...['Código', 'Produto', 'Lote', 'Validade', 'Nº de série', 'Fornecedor', 'No sistema'].map((t) => h('th', t)),
          ...(p.mostrarCodigoLido ? [h('th', 'Código bipado')] : []),
        ])]),
        h('tbody', p.itens.map((i: any, n: number) => h('tr', { key: n }, [
          h('td', { class: 'mono' }, [i.codigo_aghu || '—', i.id_unidade ? h('div', { class: 'pequeno suave' }, i.id_unidade) : null]),
          // O vínculo com o paciente é o mesmo em todos os grupos, então o rótulo é neutro.
          h('td', [i.descricao_aghu || i.xProd || '—', i.paciente ? h('div', { class: 'pequeno suave' }, `paciente ${i.paciente}`) : null]),
          h('td', { class: 'mono' }, i.nLote || '—'),
          h('td', { class: 'mono' }, f.dataBr(i.dVal) || '—'),
          h('td', { class: 'mono pequeno' }, i.numero_serie || '—'),
          h('td', { class: 'pequeno' }, i.fornecedor || '—'),
          h('td', { class: 'pequeno' }, (i.status || i.status_no_sistema) ? f.rotuloStatus(i.status || i.status_no_sistema) : '—'),
          ...(p.mostrarCodigoLido ? [h('td', { class: 'mono pequeno' }, i.codigo_lido || '—')] : []),
        ]))),
      ]),
    ]);
  },
});
</script>
