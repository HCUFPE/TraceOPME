<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Dispensar para a sala</h1>
        <p>Escolha o paciente e bipe o OPME separado para ele. No fim, a sala confere os materiais e
           confirma o recebimento com seu usuário — sem bipar de novo.</p>
      </div>
      <div class="acoes">
        <a class="botao" href="/procedimentos#novo">Abrir procedimento</a>
        <a class="botao secundario" href="/farmacia/dispensacoes">Aguardando a confirmação da sala</a>
        <a class="botao secundario" href="/farmacia">Voltar</a>
      </div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />

    <form method="get" action="/farmacia/atendimentos" class="cartao" style="display:flex;gap:.6rem;align-items:flex-end;flex-wrap:wrap">
      <div class="campo" style="margin:0"><label>Data</label>
        <input type="date" name="data" :defaultValue="d.data"></div>
      <div class="campo" style="margin:0"><label>Unidade</label>
        <select name="unidade">
          <option value="">todas</option>
          <option v-for="(u, chave) in f.unidadesAtivas()" :key="chave" :value="chave" :selected="chave === d.unidade">{{ u.rotulo }}</option>
        </select></div>
      <div class="campo" style="margin:0"><label>Prontuário ou paciente</label>
        <input type="text" name="prontuario" :defaultValue="d.prontuario"></div>
      <button class="botao secundario">Filtrar</button>
    </form>

    <div class="cartao">
      <div v-if="d.atendimentos.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Hora</th><th>Local</th><th>Prontuário</th><th>Paciente</th><th>OPME solicitado</th>
                     <th>Solicitação da sala</th><th class="num">Dispensado</th><th></th></tr></thead>
          <tbody>
            <tr v-for="a in d.atendimentos" :key="a.id_atendimento">
              <td class="pequeno">{{ a.hora_inicio || '—' }}</td>
              <td class="pequeno">{{ f.rotuloUnidade(a.unidade) }} — sala {{ a.sala }}</td>
              <td><strong>{{ a.prontuario }}</strong></td>
              <td class="pequeno">{{ a.paciente || '—' }}</td>
              <td class="pequeno" style="max-width:22rem;white-space:pre-wrap">{{ a.opme_solicitado || '—' }}</td>
              <td class="pequeno">
                <template v-if="d.solicitacoes[a.id_atendimento]">
                  <span v-if="d.solicitacoes[a.id_atendimento].cancelada" class="etiqueta cinza">pedido cancelado</span>
                  <span v-else :class="['etiqueta', !d.solicitacoes[a.id_atendimento].faltando ? 'verde' : 'amarelo']">{{ d.solicitacoes[a.id_atendimento].atendidas }}/{{ d.solicitacoes[a.id_atendimento].linhas }} atendido(s)<template v-if="d.solicitacoes[a.id_atendimento].finalizada"> · finalizada</template></span>
                  <span v-if="d.solicitacoes[a.id_atendimento].nao_solicitados" class="etiqueta vermelho"> {{ d.solicitacoes[a.id_atendimento].nao_solicitados }} sem solicitação</span>
                </template>
                <span v-else class="suave">—</span></td>
              <td class="num pequeno">
                <span v-if="a.qtd_transito" class="etiqueta amarelo">{{ a.qtd_transito }} aguardando a sala</span>
                <span v-if="a.qtd_na_sala" class="etiqueta verde">{{ a.qtd_na_sala }} na sala</span>
                <template v-if="!a.qtd_transito && !a.qtd_na_sala">—</template>
              </td>
              <td style="white-space:nowrap"><a class="botao pequeno" :href="`/bipagem/dispensar_sala?atendimento=${a.id_atendimento}`">Dispensar</a>
                <a v-if="!a.qtd_utilizados && !a.qtd_na_sala" class="botao pequeno secundario" :href="`/bipagem/dispensar_sala?atendimento=${a.id_atendimento}#cancelar`"
                   title="Procedimento cancelado: o que foi dispensado volta direto para o estoque da farmácia"> Cancelado</a></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum atendimento aberto com esses filtros. Abra o procedimento em
        <a href="/procedimentos#novo">Procedimentos → Abrir procedimento</a>.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
