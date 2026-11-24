<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Caixa <span class="mono">{{ cx.id_caixa }}</span></h1>
        <p>{{ cx.nome }} · fornecedor {{ cx.fornecedor || '—' }} ·
           <span v-if="cx.bloqueada" class="etiqueta vermelho">BLOQUEADA — conferir</span><span v-else class="etiqueta verde">liberada</span></p>
      </div>
      <div class="acoes">
        <a v-if="auth.podeAcessar('farmacia')" class="botao secundario" :href="`/farmacia/caixas-consignado/${cx.id_caixa}`">Abrir na Farmácia</a>
        <button type="button" class="botao secundario" @click="router.back()">Voltar</button>
      </div>
    </div>

    <div v-if="ev" class="cartao" style="border-left:5px solid var(--azul)">
      <h2>No momento do movimento</h2>
      <p style="margin-top:0"><strong>{{ ROTULO_EVENTO[ev.tipo] || f.capitalizar(ev.tipo) }}</strong>
         em {{ f.dataHoraBr(ev.data_evento) }} por {{ ev.usuario }}
         <template v-if="ev.prontuario">· prontuário {{ ev.prontuario }}<template v-if="ev.paciente"> ({{ ev.paciente }})</template>, sala {{ ev.sala }}</template>.<br>
         <template v-if="ev.motivo"><span class="pequeno">{{ ev.motivo }}</span><br></template>
         <span class="suave pequeno">{{ ev.observacao || '' }}</span></p>

      <div class="grade grade-2">
        <div>
          <h3>Na caixa naquele momento ({{ (d.naquele || []).length }})</h3>
          <div v-if="d.naquele?.length" class="tabela-rolagem"><table>
            <thead><tr><th>Material</th><th>AGHU</th><th>Lote</th><th>Hoje</th></tr></thead>
            <tbody>
              <tr v-for="(i, n) in d.naquele" :key="n"><td class="pequeno">{{ i.produto }}</td><td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td>
                  <td class="mono pequeno">{{ i.nLote || '—' }}</td>
                  <td><span :class="['etiqueta', f.corStatus(i.status)]">{{ f.rotuloStatus(i.status) }}</span></td></tr>
            </tbody></table></div>
          <p v-else class="vazio">Nenhum item.</p>
        </div>
        <div>
          <template v-if="ev.tipo === 'devolver_caixa'">
            <h3>Devolvidos nesta devolução ({{ (d.devolvidos || []).length }})</h3>
            <div v-for="(i, n) in d.devolvidos" :key="n" class="pequeno"><span class="mono">{{ i.codigo_aghu || '—' }}</span> · {{ i.produto }} · lote {{ i.nLote || '—' }}</div>
            <p v-if="!d.devolvidos?.length" class="vazio">—</p>
          </template>
          <template v-if="d.usados_no_atendimento?.length">
            <h3 style="margin-top:1rem">Usados da caixa neste atendimento ({{ d.usados_no_atendimento.length }})</h3>
            <div v-for="(i, n) in d.usados_no_atendimento" :key="n" class="pequeno"><span class="mono">{{ i.codigo_aghu || '—' }}</span> · {{ i.produto }} · lote {{ i.nLote || '—' }} · {{ f.dataHoraBr(i.saiu_em) }}</div>
          </template>
        </div>
      </div>
    </div>

    <div class="cartao">
      <h2>Agora — {{ cx.total }} item(ns) na caixa</h2>
      <div v-if="d.agora?.length" class="tabela-rolagem"><table>
        <thead><tr><th>Material</th><th>AGHU</th><th>Lote</th><th>Validade</th><th class="num">Qtd.</th></tr></thead>
        <tbody>
          <tr v-for="(r, n) in d.agora" :key="n"><td>{{ r.produto }}</td><td class="mono pequeno">{{ r.codigo_aghu || '—' }}</td><td class="mono">{{ r.nLote || '—' }}</td>
              <td>{{ f.dataBr(r.dVal) || '—' }}</td><td class="num"><strong>{{ r.quantidade }}</strong></td></tr>
        </tbody></table></div>
      <p v-else class="vazio">Caixa vazia.</p>
      <p v-if="cx.bloqueada" class="aviso erro" style="margin-top:.8rem">{{ cx.bloqueio_motivo }}</p>
    </div>

    <div class="cartao">
      <h2>Histórico da caixa</h2>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Quando</th><th>Movimento</th><th>Prontuário / sala</th><th>Usuário</th><th>Detalhe</th></tr></thead>
        <tbody>
          <tr v-for="h in d.historico" :key="h.id_evento"><td class="pequeno">{{ f.dataHoraBr(h.data_evento) }}</td>
              <td class="pequeno">{{ ROTULO_HIST[h.tipo] || f.capitalizar(h.tipo) }}</td>
              <td class="pequeno"><template v-if="h.prontuario">{{ h.prontuario }} · sala {{ h.sala }}</template><template v-else>—</template></td>
              <td class="pequeno">{{ h.usuario }}</td>
              <td class="pequeno">{{ h.motivo || '' }} <span class="suave">{{ h.observacao || '' }}</span>
                <template v-if="['devolver_caixa', 'devolucao_caixa_divergente', 'conferir_caixa'].includes(h.tipo)"><br><a :href="`/consultas/caixa/${cx.id_caixa}?evento=${h.id_evento}`">ver neste momento</a></template></td></tr>
          <tr v-if="!d.historico?.length"><td colspan="5" class="vazio">Sem movimentos.</td></tr>
        </tbody></table></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, auth } = useTela();
const router = useRouter();
const cx = computed(() => props.d.caixa);
const ev = computed(() => props.d.evento);
const ROTULO_EVENTO: Record<string, string> = {
  devolver_caixa: 'Devolução da caixa',
  devolucao_caixa_divergente: 'Devolução da caixa RECUSADA (contagem não bateu)',
  conferir_caixa: 'Conferência da caixa',
};
const ROTULO_HIST: Record<string, string> = {
  criar_caixa: 'Caixa criada', devolver_caixa: 'Devolução da caixa',
  devolucao_caixa_divergente: 'Devolução RECUSADA', conferir_caixa: 'Conferida e liberada',
};
</script>
