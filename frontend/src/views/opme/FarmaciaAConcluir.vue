<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Procedimentos a concluir</h1>
        <p>A sala já finalizou os materiais utilizados. Falta a farmácia dar ciência dos não utilizados
           ou resolver o que não voltou — e concluir.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />

    <div class="cartao">
      <div v-if="d.lista.length" class="tabela-rolagem"><table>
        <thead><tr><th>Procedimento</th><th>Local</th><th>Paciente</th><th class="num">Usados</th>
          <th>Situação</th><th></th></tr></thead>
        <tbody>
          <tr v-for="a in d.lista" :key="a.id_atendimento">
            <td><strong>{{ a.prontuario }}</strong><br><span class="suave pequeno">finalizado em {{ f.dataHoraBr(a.uso_finalizado_em) }} por {{ a.uso_finalizado_por }}</span></td>
            <td class="pequeno">{{ f.rotuloUnidade(a.unidade) }} — sala {{ a.sala }}</td>
            <td class="pequeno">{{ a.paciente || '—' }}</td>
            <td class="num">{{ a.usados }}</td>
            <td>
              <span v-if="a.a_conferir" class="etiqueta amarelo">{{ a.a_conferir }} não utilizado(s) — dar ciência</span>
              <span v-else-if="a.pendentes" class="etiqueta vermelho">{{ a.pendentes }} não voltou — sala conferindo</span>
              <span v-else class="etiqueta verde">pronto para concluir</span>
            </td>
            <td style="white-space:nowrap">
              <a v-if="a.a_conferir" class="botao pequeno" :href="`/devolucoes/${a.id_devolucao}`">Dar ciência</a>
              <a v-else class="botao pequeno" :href="`/farmacia/procedimento/${a.id_atendimento}`">Abrir</a>
            </td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhum procedimento aguardando a farmácia.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
