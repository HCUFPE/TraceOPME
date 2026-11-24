<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Transferir para outra farmácia</h1>
        <p>Mande material do Bloco Cirúrgico para a Hemodinâmica (ou o contrário). Bipe o que vai e finalize: o material
           sai do estoque desta farmácia na hora (“em trânsito para a farmácia”) e a outra farmácia confere e dá ciência
           em <a href="/farmacia/recebimentos">Receber material</a>. Até a ciência, dá para cancelar a transferência.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />

    <div v-if="d.a_receber" class="aviso alerta">Há <strong>{{ d.a_receber }}</strong> transferência(s) da outra farmácia esperando a
      ciência desta. <a href="/farmacia/recebimentos">Conferir agora</a></div>

    <form method="post" action="/farmacia/transferencias/novo" class="cartao" style="border-left:5px solid var(--azul, #0c3a67)">
      <h2>Nova transferência</h2>
      <div class="linha-botoes">
        <button v-for="chave in Object.keys(d.farmacias || {})" :key="chave" class="botao" name="farmacia" :value="chave"
                :class="{ secundario: d.origem && d.origem !== chave }" style="font-size:1.05rem;padding:.9rem 1.4rem">
          {{ curto(chave) }} → {{ curto(outra(chave)) }}</button>
      </div>
      <p class="pequeno suave" style="margin:.5rem 0 0">Escolha de onde sai o material. Se já houver uma transferência aberta
        nesse sentido, ela continua de onde parou.</p>
    </form>
    <p class="pequeno" style="margin:.2rem 0 .8rem">
      <template v-if="d.filtrando">Mostrando só as que saíram da {{ f.rotuloUnidade(d.origem) }} ·
        <a href="/farmacia/transferencias?todas=1">ver de todas as farmácias</a></template>
      <template v-else>Mostrando todas as farmácias.</template>
    </p>

    <div v-if="d.pendencias?.length" class="cartao" id="pendencias" style="border-left:5px solid var(--vermelho, #b3261e)">
      <h2>Não recebidos pela farmácia de destino — tratar ({{ d.pendencias.length }})</h2>
      <p class="pequeno suave">Se o item chegou depois, quem marca “recebi” é a farmácia de destino, em Receber material.</p>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Transferência</th><th>Material</th><th>AGHU</th><th>Lote</th><th>Conferido por</th><th>Tratativa</th></tr></thead>
        <tbody>
          <tr v-for="p in d.pendencias" :key="p.id_item">
            <td class="mono pequeno"><a :href="`/farmacia/transferencia/${p.id_remessa}`">{{ p.id_remessa }}</a><br>
              <span class="suave">{{ p.farmacia_origem_rotulo }} → {{ p.farmacia_rotulo }}</span></td>
            <td class="pequeno">{{ p.descricao }}</td>
            <td class="mono pequeno">{{ p.codigo_aghu || '—' }}</td>
            <td class="mono pequeno">{{ p.nLote || '—' }}</td>
            <td class="pequeno">{{ p.conferida_nome || '—' }}<br><span class="suave">{{ f.dataHoraBr(p.conferida_em) }}</span></td>
            <td>
              <form method="post" :action="`/farmacia/transferencia/item/${p.id_item}/tratar`" style="display:flex;gap:.3rem;flex-wrap:wrap;align-items:center">
                <select name="acao" required style="width:auto">
                  <option value="">— escolha —</option>
                  <option value="voltou_origem">Voltou ao estoque da farmácia de origem</option>
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
      <h2>Transferências</h2>
      <div v-if="todos.length" class="tabela-rolagem"><table>
        <thead><tr><th>Transferência</th><th>De → Para</th><th>Situação</th><th class="num">Itens</th><th>Quando</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in todos" :key="r.id_remessa">
            <td class="mono pequeno">{{ r.id_remessa }}</td>
            <td>{{ curto(r.farmacia_origem) }} → {{ curto(r.farmacia) }}</td>
            <td><SituacaoRemessa :r="r" /></td>
            <td class="num">{{ r.qtd }}</td>
            <td class="pequeno">{{ f.dataHoraBr(r.enviada_em || r.criado_em) }}</td>
            <td><a :class="['botao', 'pequeno', r.status === 'aberta' ? '' : 'secundario']" :href="`/farmacia/transferencia/${r.id_remessa}`">{{ r.status === 'aberta' ? 'Continuar' : 'Ver' }}</a></td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhuma transferência ainda.</p>
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
const NOMES: Record<string, string> = { 'BLOCO CIRURGICO': 'Bloco Cirúrgico', 'HEMODINAMICA - PDT': 'Hemodinâmica' };
const curto = (chave: string) => NOMES[chave] || chave || '—';
const outra = (chave: string) => Object.keys(props.d.farmacias || {}).find((k) => k !== chave) || '';
const todos = computed(() => [...(props.d.abertas || []), ...(props.d.enviadas || []), ...(props.d.conferidas || []),
  ...(props.d.canceladas || [])]);
</script>
