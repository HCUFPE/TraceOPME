<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Não utilizados — dar ciência</h1>
        <p>Quando a sala finaliza os materiais utilizados, o que a farmácia dispensou e não foi usado chega aqui em lista. Confira o que voltou, desmarque o que não chegou e dê ciência.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>

    <div class="cartao">
      <h2>Aguardando a farmácia ({{ d.pendentes.length }})</h2>
      <div v-if="d.pendentes.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Prontuário</th><th>Local</th><th>Devolvido por</th><th>Itens</th><th>Caixas</th><th>Finalizado em</th><th></th></tr></thead>
          <tbody>
            <tr v-for="x in d.pendentes" :key="x.id_devolucao">
              <td><strong>{{ x.prontuario }}</strong><template v-if="x.paciente"><br><span class="suave pequeno">{{ x.paciente }}</span></template></td>
              <td class="pequeno">{{ x.unidade_rotulo }}<template v-if="x.unidade_rotulo"> — </template>sala {{ x.sala }}
                <span v-if="x.outra_unidade" class="etiqueta cinza">outra farmácia</span></td>
              <td><span class="etiqueta azul">{{ x.devolvido_por }}</span></td>
              <td class="num">{{ x.qtd_itens }}</td>
              <td class="num">{{ x.qtd_caixas }}</td>
              <td class="pequeno">{{ f.dataHoraBr(x.ultimo_bip) }}</td>
              <td><a class="botao pequeno" :href="`/devolucoes/${x.id_devolucao}`">Conferir e dar ciência</a></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhuma lista aguardando a ciência da farmácia.</p>
    </div>

    <div v-if="d.confirmadas?.length" class="cartao">
      <h2>Confirmadas recentemente</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Confirmada em</th><th>Prontuário</th><th>Devolvido por</th><th>Recebido por</th><th>Recebidos</th><th>Não recebidos</th><th></th></tr></thead>
          <tbody>
            <tr v-for="x in d.confirmadas" :key="x.id_devolucao">
              <td class="pequeno">{{ f.dataHoraBr(x.confirmada_em) }}</td>
              <td>{{ x.prontuario }} <span class="suave pequeno">· sala {{ x.sala }}</span></td>
              <td class="pequeno">{{ x.devolvido_por }}</td>
              <td class="pequeno">{{ x.recebido_por }}</td>
              <td class="num">{{ x.recebidos }}</td>
              <td class="num"><span v-if="x.nao_recebidos" class="etiqueta vermelho">{{ x.nao_recebidos }}</span><template v-else>0</template></td>
              <td><a class="pequeno" :href="`/devolucoes/${x.id_devolucao}`">ver</a></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
