<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Solicitações de OPME em aberto</h1>
        <p>Pedidos da sala de procedimento que a farmácia ainda precisa atender, de qualquer data.
           O pedido sai daqui quando tudo for dispensado, quando a dispensa for finalizada ou se o procedimento for cancelado.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />
    <p class="pequeno" style="margin:.2rem 0 .8rem">
      <template v-if="d.filtrando">Mostrando só os pedidos de <strong>{{ f.rotuloUnidade(d.unidade_atual) }}</strong> ·
        <a href="/farmacia/solicitacoes?todas=1">ver de todas as unidades</a></template>
      <template v-else-if="d.unidade_atual">Mostrando todas as unidades · <a href="/farmacia/solicitacoes">só {{ f.rotuloUnidade(d.unidade_atual) }}</a></template>
      <template v-else>Mostrando todas as unidades.</template>
    </p>
    <div class="cartao">
      <div v-if="d.pedidos.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Data</th><th>Local</th><th>Prontuário</th><th>Paciente</th><th>Especialidade</th>
            <th>Pedido</th><th>Andamento</th><th></th></tr></thead>
          <tbody>
            <tr v-for="p in d.pedidos" :key="p.id_atendimento">
              <td class="pequeno">{{ f.dataBr(p.data_procedimento) }}<template v-if="p.hora_inicio"><br>{{ p.hora_inicio }}</template></td>
              <td class="pequeno">{{ f.rotuloUnidade(p.unidade) }} — sala {{ p.sala }}</td>
              <td><strong>{{ p.prontuario }}</strong></td>
              <td class="pequeno">{{ p.paciente || '—' }}</td>
              <td class="pequeno">{{ f.especialidade(p.especialidade) }}</td>
              <td class="pequeno">{{ p.criado_por }}<br><span class="suave">{{ f.dataHoraBr(p.atualizado_em) }}</span></td>
              <td><span :class="['etiqueta', p.atendidas ? 'amarelo' : 'vermelho']">{{ p.atendidas }}/{{ p.linhas }} atendido(s)</span></td>
              <td class="acoes-linha">
                <a class="botao pequeno" :href="`/bipagem/dispensar_sala?atendimento=${p.id_atendimento}`">Atender</a>
                <!-- v18.28: folha de separação para a farmácia imprimir. -->
                <a class="botao pequeno secundario" :href="`/farmacia/atendimento/${p.id_atendimento}/solicitacao/imprimir`">Imprimir</a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhuma solicitação em aberto.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>

<style scoped>
.acoes-linha { display: flex; gap: .3rem; flex-wrap: wrap; }
</style>
