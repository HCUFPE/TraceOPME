<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Caixas nas salas</h1>
        <p>A caixa de consignado vai para uma <strong>sala</strong> e fica lá o dia todo, servindo a todos os
           procedimentos daquela sala. A sala dá ciência da caixa, bipa o uso de cada item no paciente e
           devolve a caixa até as <strong>23:59</strong>. No retorno, a farmácia confere a caixa e reabastece.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />

    <form method="post" action="/farmacia/caixas-sala/enviar" class="cartao">
      <h2>Enviar caixa para a sala</h2>
      <div class="filtros">
        <div class="campo" style="flex:1">
          <label class="obrigatorio" for="codigo-caixa">Bipe a caixa</label>
          <input type="text" id="codigo-caixa" ref="campoCaixa" name="codigo" list="lista-caixas" autocomplete="off" required
                 placeholder="código da caixa (CX-…)" style="font-size:1.2rem">
          <datalist id="lista-caixas">
            <option v-for="c in d.caixas_livres" :key="c.id_caixa" :value="c.id_caixa">{{ c.nome }} · {{ c.fornecedor || '' }}</option>
          </datalist>
        </div>
        <div class="campo">
          <label class="obrigatorio">Sala de destino</label>
          <select name="local" required>
            <option value="">— escolha —</option>
            <option v-for="l in d.locais" :key="`${l[0]}|${l[1]}`" :value="`${l[0]}|${l[1]}`">{{ l[2] }}</option>
          </select>
        </div>
        <button class="botao">Enviar para a sala</button>
      </div>
      <p class="pequeno suave" style="margin:.4rem 0 0">Para a caixa ir a outra sala, ela precisa voltar à farmácia e ser conferida antes.</p>
    </form>

    <div class="cartao">
      <h2>Fora da farmácia agora ({{ d.ativos.length }})</h2>
      <div v-if="d.ativos.length" class="tabela-rolagem"><table>
        <thead><tr><th>Caixa</th><th>Sala</th><th>Situação</th><th class="num">Enviados</th><th class="num">Usados</th>
                   <th class="num">Na caixa</th><th>Enviada</th><th>Prazo</th><th></th></tr></thead>
        <tbody>
          <tr v-for="t in d.ativos" :key="t.id_turno" :style="t.fora_do_prazo || t.status === 'divergente' ? 'background:var(--vermelho-claro)' : ''">
            <td><a :href="`/farmacia/caixas-sala/${t.id_turno}`" class="mono"><strong>{{ t.id_caixa }}</strong></a>
                <br><span class="pequeno suave">{{ t.nome_caixa }}<template v-if="t.fornecedor"> · {{ t.fornecedor }}</template></span></td>
            <td>{{ t.local }}</td>
            <td>
              <span v-if="t.status === 'devolvida'" class="etiqueta amarelo">{{ t.status_rotulo }}</span>
              <span v-else-if="t.status === 'divergente'" class="etiqueta vermelho">{{ t.status_rotulo }} ({{ t.faltaram }})</span>
              <span v-else-if="t.status === 'enviada'" class="etiqueta azul">{{ t.status_rotulo }}</span>
              <span v-else class="etiqueta verde">{{ t.status_rotulo }}</span>
              <template v-if="t.recebida_nome"><br><span class="pequeno suave">ciência: {{ t.recebida_nome }}</span></template>
            </td>
            <td class="num">{{ t.qtd_enviada }}</td><td class="num">{{ t.usados }}</td><td class="num">{{ t.restam }}</td>
            <td class="pequeno">{{ f.dataHoraBr(t.enviada_em) }}<br><span class="suave">{{ t.enviada_por }}</span></td>
            <td class="pequeno"><template v-if="t.fora_do_prazo"><strong style="color:var(--vermelho)">FORA DO PRAZO</strong><br></template>
                até {{ f.dataHoraBr(t.prazo) }}</td>
            <td>
              <a v-if="t.status === 'devolvida'" class="botao pequeno" :href="`/farmacia/caixas-sala/${t.id_turno}`">Conferir a caixa</a>
              <form v-else-if="t.status === 'enviada'" method="post" :action="`/farmacia/caixas-sala/${t.id_turno}/cancelar`" data-confirmar="Cancelar o envio? Os itens voltam ao estoque.">
                <button class="botao secundario pequeno">Cancelar envio</button></form>
              <a v-else-if="t.status === 'divergente'" class="botao secundario pequeno" :href="`/farmacia/caixas-consignado/${t.id_caixa}`">Conferir e liberar</a>
            </td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhuma caixa fora da farmácia.</p>
    </div>

    <div v-if="d.recentes?.length" class="cartao">
      <h2>Últimas conferidas</h2>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Caixa</th><th>Sala</th><th>Dia</th><th class="num">Enviados</th><th class="num">Usados</th><th class="num">Voltaram</th><th>Conferida por</th></tr></thead>
        <tbody>
          <tr v-for="t in d.recentes" :key="t.id_turno"><td><a class="mono" :href="`/farmacia/caixas-sala/${t.id_turno}`">{{ t.id_caixa }}</a></td><td>{{ t.local }}</td>
              <td>{{ f.dataBr(t.data) }}</td><td class="num">{{ t.qtd_enviada }}</td><td class="num">{{ t.qtd_usada ?? '—' }}</td>
              <td class="num">{{ t.qtd_voltou ?? '—' }}</td>
              <td class="pequeno">{{ t.status === 'cancelada' ? t.status_rotulo : (t.conferida_nome || '—') }}</td></tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
const campoCaixa = ref<HTMLInputElement | null>(null);
onMounted(() => campoCaixa.value?.focus());
</script>
