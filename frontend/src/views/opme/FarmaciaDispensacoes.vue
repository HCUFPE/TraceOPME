<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Dispensações aguardando a confirmação da sala</h1>
        <p>OPME que saiu da farmácia e ainda não teve o recebimento confirmado pelo operador da sala.</p>
      </div>
      <div class="acoes">
        <a class="botao" href="/farmacia/atendimentos">Nova dispensação</a>
        <a class="botao secundario" href="/farmacia">Voltar</a>
      </div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />

    <div class="cartao">
      <h2>Aguardando ({{ d.pendentes.length }})</h2>
      <div v-if="d.pendentes.length" class="tabela-rolagem"><table>
        <thead><tr><th>Desde</th><th>Prontuário</th><th>Local</th><th>Dispensado por</th><th class="num">Itens</th><th></th></tr></thead>
        <tbody>
          <tr v-for="x in d.pendentes" :key="x.id_dispensacao">
            <td class="pequeno">{{ f.dataHoraBr(x.criado_em) }}</td>
            <td><strong>{{ x.prontuario }}</strong><template v-if="x.paciente"><br><span class="suave pequeno">{{ x.paciente }}</span></template></td>
            <td class="pequeno">{{ f.rotuloUnidade(x.unidade) }} — sala {{ x.sala }}</td>
            <td class="pequeno">{{ x.criado_por }}</td>
            <td class="num">{{ x.qtd }}</td>
            <td><a class="botao pequeno" :href="`/dispensacoes/${x.id_dispensacao}`">Abrir</a></td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhuma dispensação aguardando.</p>
    </div>

    <div v-if="d.confirmadas?.length" class="cartao">
      <h2>Confirmadas recentemente</h2>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Confirmada em</th><th>Prontuário</th><th>Local</th><th>Dispensado por</th><th>Recebido por (sala)</th><th class="num">Itens</th><th></th></tr></thead>
        <tbody>
          <tr v-for="x in d.confirmadas" :key="x.id_dispensacao">
            <td class="pequeno">{{ f.dataHoraBr(x.confirmada_em) }}</td>
            <td>{{ x.prontuario }}</td>
            <td class="pequeno">{{ f.rotuloUnidade(x.unidade) }} — sala {{ x.sala }}</td>
            <td class="pequeno">{{ x.criado_por }}</td>
            <td><span class="etiqueta verde">{{ x.recebido_por }}</span></td>
            <td class="num">{{ x.qtd }}</td>
            <td><a class="pequeno" :href="`/dispensacoes/${x.id_dispensacao}`">ver</a></td>
          </tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
