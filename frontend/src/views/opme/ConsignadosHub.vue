<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Consignados</h1>
        <p>Saldo de empenho por código consignado (com o AGHU associado).</p>
      </div>
    </div>

    <div v-if="d.alertas?.length" class="cartao" style="margin-bottom:1.25rem;border-left:5px solid var(--vermelho)">
      <h2>{{ d.alertas.length }} alerta(s) de saldo</h2>
      <div v-for="a in d.alertas" :key="a.id_alerta" style="padding:.6rem 0;border-bottom:1px solid var(--borda)">
        <strong class="pequeno">{{ a.titulo }}</strong>
        <p class="pequeno" style="margin:.2rem 0">{{ a.mensagem }}</p>
        <template v-if="a.link"><a class="pequeno" :href="a.link">Abrir empenho</a> · </template>
        <span class="suave pequeno">{{ f.dataHoraBr(a.criado_em) }}</span>
        <form method="post" :action="`/alertas/${a.id_alerta}/resolver`" style="display:inline;margin-left:.5rem">
          <button class="botao secundario pequeno">Marcar como resolvido</button>
        </form>
      </div>
    </div>

    <div class="grade grade-3">
      <a :class="['acao-card', 'cor-roxo', { alta: d.pendentes }]" href="/consignados/pendentes">
        <h3>Usos sem empenho</h3>
        <div class="numero">{{ d.pendentes }}</div>
        <p class="rotulo">consignados usados que não tinham empenho com saldo — vincule à mão</p>
      </a>
      <a class="acao-card cor-roxo" href="/consignados/empenhos">
        <h3>Empenhos</h3>
        <p class="rotulo">Ver saldo, histórico de vínculos e encerrar empenho.</p>
      </a>
      <a class="acao-card cor-roxo" href="/consignados/associacoes">
        <h3>Código consignado × AGHU</h3>
        <p class="rotulo">Associe cada código consignado ao código AGHU. O empenho é cadastrado pelo código consignado.</p>
      </a>
      <a class="acao-card cor-roxo" href="/consignados/empenhos/novo">
        <h3>Cadastrar empenho</h3>
        <p class="rotulo">Registre um novo empenho recebido da gestão.</p>
      </a>
    </div>

    <div class="cartao" style="margin-top:1.5rem">
      <h2>Empenhos ativos</h2>
      <div v-if="d.ativos?.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Nº</th><th>Fornecedor</th><th>Cód. consignado → AGHU</th><th>Material</th>
                     <th class="num">Saldo</th><th></th></tr></thead>
          <tbody>
            <tr v-for="e in d.ativos" :key="e.id_empenho">
              <td class="mono">{{ e.identificacao || e.numero }}</td>
              <td>{{ e.fornecedor }}</td>
              <td><CodigosEmpenho :e="e" /></td>
              <td>{{ e.material }}</td>
              <td class="num">
                <span :class="['etiqueta', e.no_limite ? 'vermelho' : (e.percentual_usado >= 60 ? 'amarelo' : 'verde')]">
                  {{ e.saldo }} de {{ e.quantidade_total }}<template v-if="e.no_limite"> · pedir mais empenho</template>
                </span>
              </td>
              <td><a class="botao pequeno secundario" :href="`/consignados/empenhos/${e.id_empenho}`">Abrir</a></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum empenho ativo. <a href="/consignados/empenhos/novo">Cadastrar agora</a>.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import CodigosEmpenho from '../../components/opme/CodigosEmpenho.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
