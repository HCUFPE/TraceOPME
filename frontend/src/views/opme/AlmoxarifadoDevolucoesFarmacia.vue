<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Devoluções das farmácias</h1>
        <p>Material que as farmácias devolveram ao almoxarifado. Confira — bipando ou pela lista — e dê ciência:
           o que for recebido volta ao estoque do almoxarifado; o que não chegar vira pendência.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/almoxarifado">Voltar</a></div>
    </div>

    <div class="cartao" style="border-left:5px solid var(--amarelo, #b58100)">
      <h2>Para conferir e dar ciência ({{ d.enviadas.length }})</h2>
      <div v-if="d.enviadas.length" class="tabela-rolagem"><table>
        <thead><tr><th>Devolução</th><th>Farmácia</th><th class="num">Itens</th><th>Devolvido</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in d.enviadas" :key="r.id_remessa">
            <td class="mono pequeno">{{ r.id_remessa }}</td><td>{{ r.farmacia_rotulo }}</td><td class="num">{{ r.qtd }}</td>
            <td class="pequeno">{{ r.enviada_por }} · {{ f.dataHoraBr(r.enviada_em) }}<template v-if="r.observacao"><br><span class="suave">{{ r.observacao }}</span></template></td>
            <td><a class="botao pequeno" :href="`/almoxarifado/devolucao-farmacia/${r.id_remessa}`">Conferir e dar ciência</a></td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhuma devolução aguardando ciência.</p>
      <p v-if="d.abertas?.length" class="pequeno suave" style="margin:.6rem 0 0">{{ d.abertas.length }} devolução(ões) ainda em montagem na farmácia.</p>
    </div>

    <div v-if="d.pendencias?.length" class="cartao" style="border-left:5px solid var(--vermelho, #b3261e)">
      <h2>Não recebidos — pendências ({{ d.pendencias.length }})</h2>
      <p class="pequeno suave">Itens devolvidos que não chegaram na conferência. Se chegou depois, marque “recebi”.
        Se não chegou, a farmácia registra a tratativa (voltou ao estoque dela ou divergência).</p>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Devolução</th><th>Farmácia</th><th>Material</th><th>AGHU</th><th>Lote</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in d.pendencias" :key="p.id_item">
            <td class="mono pequeno">{{ p.id_remessa }}</td><td class="pequeno">{{ p.farmacia_rotulo }}</td>
            <td class="pequeno">{{ p.descricao }}</td>
            <td class="mono pequeno">{{ p.codigo_aghu || '—' }}</td><td class="mono pequeno">{{ p.nLote || '—' }}</td>
            <td><form method="post" :action="`/almoxarifado/devolucao-farmacia/item/${p.id_item}/recebi`" style="margin:0"
                      data-confirmar="Confirmar que este item chegou ao almoxarifado?">
              <button class="botao secundario pequeno">recebi</button></form></td>
          </tr>
        </tbody>
      </table></div>
    </div>

    <div v-if="historico.length" class="cartao">
      <h2>Conferidas e canceladas recentemente</h2>
      <ul class="pequeno lista" style="margin:0 0 0 1rem">
        <li v-for="r in historico" :key="r.id_remessa"><a :href="`/almoxarifado/devolucao-farmacia/${r.id_remessa}`" class="mono">{{ r.id_remessa }}</a>
          · {{ r.farmacia_rotulo }} · {{ r.qtd }} item(ns) · <SituacaoRemessa :r="r" quem="almoxarifado" /></li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import SituacaoRemessa from '../../components/opme/SituacaoRemessa.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const historico = computed(() => [...(props.d.conferidas || []), ...(props.d.canceladas || [])]);
</script>
