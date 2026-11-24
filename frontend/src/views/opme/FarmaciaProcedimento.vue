<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Procedimento — prontuário {{ at.prontuario }}</h1>
        <p><strong>{{ d.descricao }}</strong><template v-if="at.paciente"> · {{ at.paciente }}</template></p>
        <p v-if="d.finalizado" class="pequeno">Materiais utilizados finalizados pela sala em
          {{ f.dataHoraBr(at.uso_finalizado_em) }} por {{ at.uso_finalizado_por }}.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia/procedimentos-a-concluir">Voltar</a></div>
    </div>

    <div v-if="at.status === 'encerrado'" class="aviso sucesso">Procedimento encerrado em {{ f.dataHoraBr(at.encerrado_em) }} por {{ at.encerrado_por }}.</div>
    <div v-else-if="!d.finalizado" class="aviso info">A sala ainda não finalizou os materiais utilizados deste procedimento.</div>
    <div v-else-if="d.devolucao" class="aviso alerta">A lista de não utilizados está aguardando a sua ciência.
      <a class="botao pequeno" :href="`/devolucoes/${d.devolucao.id_devolucao}`">Conferir e dar ciência</a></div>

    <div v-if="at.status === 'aberto' && d.finalizado && !d.devolucao" class="cartao"
         :style="`border-left:5px solid var(--${d.pendencias.total ? 'vermelho' : 'verde'})`">
      <template v-if="d.pendencias.total">
        <h2>Não voltou para a farmácia ({{ d.pendencias.total }})</h2>
        <p class="pequeno suave">A sala foi avisada para conferir. Se ela bipar o uso no paciente, o item sai daqui
          sozinho. Se o material chegou de volta, marque “Recebi de volta”.</p>
        <div class="tabela-rolagem"><table>
          <thead><tr><th>AGHU</th><th>Material</th><th>Lote</th><th>Validade</th><th></th></tr></thead>
          <tbody>
            <tr v-for="i in d.pendencias.itens" :key="i.id_unidade"><td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td><td>{{ i.descritivo_hospital || i.xProd }}</td>
              <td class="mono">{{ i.nLote || '—' }}</td><td class="pequeno">{{ f.dataBr(i.dVal) || '—' }}</td>
              <td><form method="post" :action="`/farmacia/procedimento/${at.id_atendimento}/receber`" style="margin:0">
                <input type="hidden" name="id_unidade" :value="i.id_unidade">
                <button class="botao pequeno">Recebi de volta</button></form></td></tr>
            <tr v-for="c in d.pendencias.caixas" :key="c.id_caixa"><td>—</td><td><strong>Caixa <span class="mono">{{ c.id_caixa }}</span></strong> {{ c.nome }} — {{ c.qtd }} item(ns)</td>
              <td>—</td><td>—</td>
              <td><form method="post" :action="`/farmacia/procedimento/${at.id_atendimento}/receber`" style="margin:0">
                <input type="hidden" name="id_caixa" :value="c.id_caixa">
                <button class="botao pequeno">Recebi a caixa</button></form></td></tr>
          </tbody>
        </table></div>
      </template>
      <template v-else>
        <h2>Tudo certo</h2>
        <p class="pequeno suave">Nada pendente: tudo foi usado no paciente ou voltou para a farmácia.</p>
      </template>
      <form method="post" :action="`/farmacia/procedimento/${at.id_atendimento}/concluir`" style="margin-top:1rem"
            data-confirmar="Concluir este procedimento? Depois disso, só a supervisão reabre.">
        <button class="botao" :disabled="!!d.pendencias.total" :title="d.pendencias.total ? 'Resolva o que não voltou primeiro' : ''">Concluir procedimento</button>
      </form>
    </div>

    <div class="cartao">
      <h2>Usados no paciente ({{ d.usados.length }})</h2>
      <div v-if="d.usados.length" class="tabela-rolagem"><table>
        <thead><tr><th>AGHU</th><th>Material</th><th>Lote</th><th>Validade</th></tr></thead>
        <tbody>
          <tr v-for="m in d.usados" :key="m.id_unidade"><td class="mono pequeno">{{ m.codigo_aghu || '—' }}</td><td>{{ m.descritivo_hospital || m.xProd }}</td>
            <td class="mono">{{ m.nLote || '—' }}</td><td class="pequeno">{{ f.dataBr(m.dVal) || '—' }}</td></tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhum material usado.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const at = computed(() => props.d.atendimento);
</script>
