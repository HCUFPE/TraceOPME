<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Enviar para a farmácia</h1>
        <p>Escolha a farmácia de destino, bipe o material e finalize o envio. A farmácia confere e dá ciência;
           o que ela não receber volta para cá como pendência.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/almoxarifado">Voltar</a></div>
    </div>

    <form method="post" action="/almoxarifado/envios/novo" class="cartao" style="border-left:5px solid var(--azul, #0c3a67)">
      <h2>Novo envio para:</h2>
      <div class="linha-botoes">
        <button v-for="(rotulo, chave) in d.farmacias" :key="chave" class="botao" name="farmacia" :value="chave"
                style="font-size:1.1rem;padding:.9rem 1.4rem">{{ rotulo }}</button>
      </div>
      <p class="pequeno suave" style="margin:.5rem 0 0">Se já houver um envio aberto para essa farmácia, ele continua de onde parou.</p>
    </form>

    <div v-if="d.devolucoes_a_conferir" class="aviso alerta">
      <strong>{{ d.devolucoes_a_conferir }} devolução(ões) das farmácias</strong> aguardando a ciência do almoxarifado.
      <a href="/almoxarifado/devolucoes-farmacia">Conferir e dar ciência</a></div>

    <div v-if="d.pendencias?.length" class="cartao" id="pendencias" style="border-left:5px solid var(--vermelho, #b3261e)">
      <h2>Não recebidos pela farmácia — tratar ({{ d.pendencias.length }})</h2>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Envio</th><th>Farmácia</th><th>Material</th><th>AGHU</th><th>Lote</th><th>Conferido por</th><th>Tratativa</th></tr></thead>
        <tbody>
          <tr v-for="p in d.pendencias" :key="p.id_item">
            <td class="mono pequeno"><a :href="`/almoxarifado/envio/${p.id_remessa}`">{{ p.id_remessa }}</a></td>
            <td class="pequeno">{{ p.farmacia_rotulo }}</td>
            <td class="pequeno">{{ p.descricao }}</td>
            <td class="mono pequeno">{{ p.codigo_aghu || '—' }}</td>
            <td class="mono pequeno">{{ p.nLote || '—' }}</td>
            <td class="pequeno">{{ p.conferida_nome || '—' }}<br><span class="suave">{{ f.dataHoraBr(p.conferida_em) }}</span></td>
            <td>
              <form method="post" :action="`/almoxarifado/envio/item/${p.id_item}/tratar`" style="display:flex;gap:.3rem;flex-wrap:wrap;align-items:center">
                <select name="acao" required style="width:auto">
                  <option value="">— escolha —</option>
                  <option value="voltou_almoxarifado">Voltou ao almoxarifado</option>
                  <option value="divergencia">Divergência / extravio</option>
                </select>
                <input type="text" name="motivo" placeholder="motivo (obrigatório na divergência)" style="width:14rem">
                <button class="botao secundario pequeno">registrar</button>
              </form>
              <span class="pequeno suave">Se chegou na farmácia, ela marca “recebi” na tela dela.</span>
            </td>
          </tr>
        </tbody>
      </table></div>
    </div>

    <div class="cartao">
      <h2>Envios</h2>
      <div v-if="todos.length" class="tabela-rolagem"><table>
        <thead><tr><th>Envio</th><th>Farmácia</th><th>Situação</th><th class="num">Itens</th><th>Quando</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in todos" :key="r.id_remessa">
            <td class="mono pequeno">{{ r.id_remessa }}</td>
            <td>{{ r.farmacia_rotulo }}</td>
            <td><SituacaoRemessa :r="r" /></td>
            <td class="num">{{ r.qtd }}</td>
            <td class="pequeno">{{ f.dataHoraBr(r.enviada_em || r.criado_em) }}</td>
            <td><a :class="['botao', 'pequeno', r.status === 'aberta' ? '' : 'secundario']" :href="`/almoxarifado/envio/${r.id_remessa}`">{{ r.status === 'aberta' ? 'Continuar' : 'Ver' }}</a></td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhum envio ainda.</p>
      <p class="pequeno suave" style="margin:.6rem 0 0">Enquanto a farmácia não dá ciência, abra o envio para <strong>cancelar</strong> —
        os itens voltam ao estoque do almoxarifado.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import SituacaoRemessa from '../../components/opme/SituacaoRemessa.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const todos = computed(() => [...(props.d.abertas || []), ...(props.d.enviadas || []), ...(props.d.conferidas || []),
  ...(props.d.canceladas || [])]);
</script>
