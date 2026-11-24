<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Devolver ao almoxarifado</h1>
        <p>Bipe o material que volta para o almoxarifado e finalize a devolução. Ele sai do estoque da farmácia na hora
           (“em devolução para o almoxarifado”) e o almoxarifado confere e dá ciência — bipando ou pela lista.
           Até a ciência, dá para cancelar a devolução.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />

    <form method="post" action="/farmacia/devolucoes-almox/novo" class="cartao" style="border-left:5px solid var(--azul, #0c3a67)">
      <h2>Nova devolução ao almoxarifado, saindo da:</h2>
      <div class="linha-botoes">
        <button v-for="(rotulo, chave) in d.farmacias" :key="chave" class="botao" name="farmacia" :value="chave"
                :class="{ secundario: d.unidade_atual && d.unidade_atual !== chave }"
                style="font-size:1.1rem;padding:.9rem 1.4rem">{{ rotulo }}</button>
      </div>
      <p class="pequeno suave" style="margin:.5rem 0 0">Se já houver uma devolução aberta dessa farmácia, ela continua de onde parou.</p>
    </form>
    <p class="pequeno" style="margin:.2rem 0 .8rem">
      <template v-if="d.filtrando">Mostrando só {{ f.rotuloUnidade(d.unidade_atual) }} · <a href="/farmacia/devolucoes-almox?todas=1">ver de todas as farmácias</a></template>
      <template v-else>Mostrando todas as farmácias.</template>
    </p>

    <div v-if="d.pendencias?.length" class="cartao" id="pendencias" style="border-left:5px solid var(--vermelho, #b3261e)">
      <h2>Não recebidos pelo almoxarifado — tratar ({{ d.pendencias.length }})</h2>
      <p class="pequeno suave">Se o item chegou no almoxarifado depois, quem marca “recebi” é o almoxarifado.</p>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Devolução</th><th>Material</th><th>AGHU</th><th>Lote</th><th>Conferido por</th><th>Tratativa</th></tr></thead>
        <tbody>
          <tr v-for="p in d.pendencias" :key="p.id_item">
            <td class="mono pequeno"><a :href="`/farmacia/devolucao-almox/${p.id_remessa}`">{{ p.id_remessa }}</a></td>
            <td class="pequeno">{{ p.descricao }}</td>
            <td class="mono pequeno">{{ p.codigo_aghu || '—' }}</td>
            <td class="mono pequeno">{{ p.nLote || '—' }}</td>
            <td class="pequeno">{{ p.conferida_nome || '—' }}<br><span class="suave">{{ f.dataHoraBr(p.conferida_em) }}</span></td>
            <td>
              <form method="post" :action="`/farmacia/devolucao-almox/item/${p.id_item}/tratar`" style="display:flex;gap:.3rem;flex-wrap:wrap;align-items:center">
                <select name="acao" required style="width:auto">
                  <option value="">— escolha —</option>
                  <option value="voltou_farmacia">Voltou ao estoque da farmácia</option>
                  <option value="divergencia">Divergência / extravio</option>
                </select>
                <input type="text" name="motivo" placeholder="motivo (obrigatório na divergência)" style="width:14rem">
                <button class="botao secundario pequeno">registrar</button>
              </form>
            </td>
          </tr>
        </tbody>
      </table></div>
    </div>

    <div class="cartao">
      <h2>Devoluções</h2>
      <div v-if="todos.length" class="tabela-rolagem"><table>
        <thead><tr><th>Devolução</th><th>Farmácia</th><th>Situação</th><th class="num">Itens</th><th>Quando</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in todos" :key="r.id_remessa">
            <td class="mono pequeno">{{ r.id_remessa }}</td>
            <td>{{ r.farmacia_rotulo }}</td>
            <td><SituacaoRemessa :r="r" quem="almoxarifado" /></td>
            <td class="num">{{ r.qtd }}</td>
            <td class="pequeno">{{ f.dataHoraBr(r.enviada_em || r.criado_em) }}</td>
            <td><a :class="['botao', 'pequeno', r.status === 'aberta' ? '' : 'secundario']" :href="`/farmacia/devolucao-almox/${r.id_remessa}`">{{ r.status === 'aberta' ? 'Continuar' : 'Ver' }}</a></td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhuma devolução ainda.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import SituacaoRemessa from '../../components/opme/SituacaoRemessa.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const todos = computed(() => [...(props.d.abertas || []), ...(props.d.enviadas || []), ...(props.d.conferidas || []),
  ...(props.d.canceladas || [])]);
</script>
