<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Código consignado × AGHU</h1>
        <p>Cada código consignado (o código do item no contrato com o fornecedor) aponta para um código AGHU. O empenho é
           cadastrado pelo código consignado, e as tabelas de empenho mostram os dois números.</p>
      </div>
      <div class="acoes">
        <a class="botao" href="/consignados/empenhos/novo">Cadastrar empenho</a>
        <a class="botao secundario" href="/consignados">Voltar</a>
      </div>
    </div>

    <div class="grade grade-2">
      <form method="post" action="/consignados/associacoes" class="cartao" id="form-associacao">
        <h2>{{ ed ? `Editar ${ed.codigo_consignado}` : 'Nova associação' }}</h2>
        <div class="grade grade-2">
          <div class="campo"><label class="obrigatorio" for="as-consignado">Código consignado</label>
            <input type="text" id="as-consignado" name="codigo_consignado" required :defaultValue="ed?.codigo_consignado"
                   :readonly="!!ed" autocomplete="off"></div>
          <div class="campo"><label class="obrigatorio" for="as-aghu">Código AGHU</label>
            <input type="text" id="as-aghu" name="codigo_aghu" required :defaultValue="ed?.codigo_aghu" autocomplete="off"
                   @input="aghu = ($event.target as HTMLInputElement).value">
            <DescritivoHc :codigo="aghu" /></div>
          <div class="campo"><label for="as-fornecedor">Fornecedor <span class="opcional">(opcional)</span></label>
            <input type="text" id="as-fornecedor" name="fornecedor" :defaultValue="ed?.fornecedor"></div>
          <div class="campo"><label for="as-descricao">Descrição no contrato <span class="opcional">(opcional)</span></label>
            <input type="text" id="as-descricao" name="descricao" :defaultValue="ed?.descricao"></div>
        </div>
        <div class="linha-botoes">
          <button class="botao">{{ ed ? 'Salvar' : 'Associar' }}</button>
          <a v-if="ed" class="botao secundario" href="/consignados/associacoes">Cancelar edição</a>
        </div>
        <p class="pequeno suave" style="margin:.5rem 0 0">Gravar um código que já existe troca o AGHU dele.</p>
      </form>

      <form method="post" action="/consignados/associacoes/importar" enctype="multipart/form-data" class="cartao">
        <h2>Importar de planilha</h2>
        <p class="pequeno">Uma linha por código. Colunas: <strong>Código consignado</strong> e <strong>Código AGHU</strong>
          (opcionais: Fornecedor, Descrição). A ordem não importa — o sistema reconhece pelo título.</p>
        <div class="campo"><label class="obrigatorio">Planilha (.xlsx ou .csv)</label>
          <input type="file" name="arquivo" accept=".xlsx,.csv" required></div>
        <button class="botao secundario">Importar</button>
      </form>
    </div>

    <div class="cartao">
      <form method="get" action="/consignados/associacoes" style="display:flex;gap:.5rem;align-items:flex-end;flex-wrap:wrap">
        <div class="campo" style="margin:0;flex:1;min-width:16rem"><label for="as-termo">Buscar</label>
          <input type="text" id="as-termo" name="termo" :defaultValue="d.termo" placeholder="código consignado, AGHU, fornecedor ou descrição"></div>
        <button class="botao secundario">Buscar</button>
      </form>
      <h2 style="margin-top:1rem">Associações ({{ d.associacoes.length }})</h2>
      <div v-if="d.associacoes.length" class="tabela-rolagem"><table>
        <thead><tr><th>Código consignado</th><th>Código AGHU</th><th>Descrição HC</th><th>Fornecedor</th>
                   <th class="num">Empenhos ativos</th><th>Atualizado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="a in d.associacoes" :key="a.codigo_consignado">
            <td class="mono"><strong>{{ a.codigo_consignado }}</strong></td>
            <td class="mono">{{ a.codigo_aghu }}</td>
            <td class="pequeno">{{ a.descritivo_hospital || a.descricao || '—' }}</td>
            <td class="pequeno">{{ a.fornecedor || '—' }}</td>
            <td class="num">{{ a.empenhos_ativos }}</td>
            <td class="pequeno">{{ a.atualizado_por || a.criado_por }} · {{ f.dataHoraBr(a.atualizado_em || a.criado_em) }}</td>
            <td style="white-space:nowrap">
              <a class="botao secundario pequeno" :href="`/consignados/associacoes?editar=${encodeURIComponent(a.codigo_consignado)}`">editar</a>
              <form v-if="!a.empenhos_ativos" method="post" action="/consignados/associacoes/excluir" style="display:inline"
                    :data-confirmar="`Excluir a associação ${a.codigo_consignado} → AGHU ${a.codigo_aghu}?`">
                <input type="hidden" name="codigo_consignado" :value="a.codigo_consignado">
                <button class="botao secundario pequeno">excluir</button></form>
            </td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhuma associação cadastrada{{ d.termo ? ' com esse filtro' : '' }}.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import DescritivoHc from '../../components/opme/DescritivoHc.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const ed = computed(() => props.d.editando);
const aghu = ref(props.d.editando?.codigo_aghu || '');
</script>
