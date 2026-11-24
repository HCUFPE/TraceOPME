<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Farmácia</h1>
      </div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />

    <div v-if="d.alertas?.length" class="cartao" style="margin-bottom:1.25rem;border-left:5px solid var(--vermelho)">
      <h2>{{ d.alertas.length }} alerta(s)</h2>
      <div v-for="a in d.alertas" :key="a.id_alerta" style="padding:.6rem 0;border-bottom:1px solid var(--borda)">
        <strong class="pequeno">{{ a.titulo }}</strong>
        <p class="pequeno" style="margin:.2rem 0;white-space:pre-wrap">{{ a.mensagem }}</p>
        <template v-if="a.link"><a class="pequeno" :href="a.link">Abrir</a> · </template>
        <span class="suave pequeno">{{ f.dataHoraBr(a.criado_em) }}</span>
        <form method="post" :action="`/alertas/${a.id_alerta}/resolver`" style="display:inline;margin-left:.5rem">
          <button class="botao secundario pequeno">Marcar como resolvido</button>
        </form>
      </div>
    </div>

    <!-- v18.16: faixas com nome, uma cor por faixa e grade que se ajusta (sem cartão órfão) -->
    <section class="faixa-acoes">
      <h2>Receber e cadastrar</h2>
      <div class="linha-cartoes">
        <a :class="['acao-card', 'cor-marinho', { alta: d.envios_a_receber || d.envios_pendencias || d.transferencias_a_receber }]" href="/farmacia/recebimentos">
          <h3>Receber material</h3>
          <div class="numero">{{ receberNumero }}</div>
          <p class="rotulo">
            <template v-if="aReceber">envio(s) do almoxarifado<template v-if="d.transferencias_a_receber"> e <strong>{{ d.transferencias_a_receber }} transferência(s) da outra farmácia</strong></template> para conferir<template v-if="d.envios_pendencias"><br><strong>{{ d.envios_pendencias }} item(ns) não recebido(s) — tratar</strong></template></template>
            <template v-else-if="d.envios_pendencias"><strong>item(ns) não recebido(s) — tratar</strong></template>
            <template v-else>nada do almoxarifado para conferir</template></p>
        </a>
        <a class="acao-card cor-marinho" href="/farmacia/transferencias">
          <h3>Transferir para outra farmácia</h3>
          <p class="rotulo">Bloco ↔ Hemodinâmica.</p>
        </a>
        <a class="acao-card cor-marinho" href="/farmacia/manual">
          <h3>Cadastro manual</h3>
          <p class="rotulo">Direto no estoque da farmácia.</p>
        </a>
      </div>
    </section>

    <section class="faixa-acoes">
      <h2>Dispensar</h2>
      <div class="linha-cartoes">
        <a :class="['acao-card', 'cor-verde', { alta: d.pedidos_opme_abertos }]" href="/farmacia/solicitacoes">
          <h3>Solicitações de OPME da sala</h3>
          <div class="numero">{{ d.pedidos_opme_abertos || 0 }}</div>
          <p class="rotulo">pedido(s) em aberto para atender</p>
        </a>
        <a class="acao-card cor-verde" href="/farmacia/atendimentos">
          <h3>Dispensar para a sala</h3>
          <p class="rotulo">Escolher o paciente e bipar.</p>
        </a>
        <a :class="['acao-card', 'cor-verde', { alta: d.dispensacoes_pendentes }]" href="/farmacia/dispensacoes">
          <h3>Aguardando a confirmação da sala</h3>
          <div class="numero">{{ d.dispensacoes_pendentes }}</div>
          <p class="rotulo">a sala ainda não confirmou</p>
        </a>
        <a class="acao-card cor-verde" href="/farmacia/saidas-outros">
          <h3>Outros procedimentos</h3>
          <p class="rotulo">Dispensar fora do fluxo de sala/paciente e ver as saídas.</p>
        </a>
      </div>
    </section>

    <section class="faixa-acoes">
      <h2>Conferir e dar ciência</h2>
      <div class="linha-cartoes">
        <a :class="['acao-card', 'cor-amarelo', { alta: d.a_concluir }]" href="/farmacia/procedimentos-a-concluir">
          <h3>Procedimentos a concluir</h3>
          <div class="numero">{{ d.a_concluir }}</div>
          <p class="rotulo">Material que não voltou.</p>
        </a>
        <a :class="['acao-card', 'cor-amarelo', { alta: d.devolucoes_pendentes }]" href="/farmacia/devolucoes">
          <h3>Não utilizados — dar ciência</h3>
          <div class="numero">{{ d.devolucoes_pendentes }}</div>
          <p class="rotulo">O que sobrou na sala.</p>
        </a>
        <a :class="['acao-card', 'cor-amarelo', { alta: d.usos_sem_dispensacao }]" href="/farmacia/usos-sem-dispensacao">
          <h3>Usos sem dispensação — dar ciência</h3>
          <div class="numero">{{ d.usos_sem_dispensacao }}</div>
          <p class="rotulo">Dar ciência de cada um.</p>
        </a>
        <a v-if="d.nao_recebidos" class="acao-card cor-amarelo alta" href="/farmacia/nao-recebidos">
          <h3>Não recebidos pela sala</h3>
          <div class="numero">{{ d.nao_recebidos }}</div>
          <p class="rotulo">item(ns) a localizar</p>
        </a>
      </div>
    </section>

    <section class="faixa-acoes">
      <h2>Caixas de consignado</h2>
      <div class="linha-cartoes">
        <a :class="['acao-card', 'cor-roxo', { alta: d.caixas_chegando }]" href="/farmacia/caixas-consignado">
          <h3>Caixas de consignado</h3>
          <div class="numero">{{ d.caixas.length }}</div>
          <p class="rotulo">Montar caixa e etiqueta.
            <template v-if="d.caixas_chegando"><br><strong>{{ d.caixas_chegando }} caixa(s) chegando do almoxarifado — dar ciência</strong></template></p>
        </a>
        <a :class="['acao-card', 'cor-roxo', { alta: d.caixas_sala.devolvidas || d.caixas_sala.fora_do_prazo || d.caixas_sala.divergentes }]" href="/farmacia/caixas-sala">
          <h3>Caixas nas salas</h3>
          <div class="numero">{{ d.caixas_sala.na_sala + d.caixas_sala.enviadas }}</div>
          <p class="rotulo">caixa(s) na sala pelo dia<template v-if="d.caixas_sala.devolvidas"> · <strong>{{ d.caixas_sala.devolvidas }} devolvida(s) para conferir</strong></template><template v-if="d.caixas_sala.fora_do_prazo"> · <strong>{{ d.caixas_sala.fora_do_prazo }} fora do prazo</strong></template><template v-if="d.caixas_sala.divergentes"> · <strong>{{ d.caixas_sala.divergentes }} com pendência</strong></template>.</p>
        </a>
        <a :class="['acao-card', 'cor-roxo', { alta: d.bloqueadas }]" href="/farmacia/caixas-consignado">
          <h3>Caixas bloqueadas — conferir</h3>
          <div class="numero">{{ d.bloqueadas }}</div>
          <p class="rotulo">Contagem diferente — conferir.</p>
        </a>
      </div>
    </section>

    <section class="faixa-acoes">
      <h2>Fechar o dia e consultar</h2>
      <div class="linha-cartoes cinco">
        <a :class="['acao-card', 'cor-azul', { alta: d.devolucoes_almox_pendencias }]" href="/farmacia/devolucoes-almox">
          <h3>Devolver ao almoxarifado</h3>
          <div v-if="d.devolucoes_almox_aguardando" class="numero">{{ d.devolucoes_almox_aguardando }}</div>
          <p class="rotulo">Bipar o que volta.
            <template v-if="d.devolucoes_almox_aguardando"><br>{{ d.devolucoes_almox_aguardando }} aguardando o almoxarifado</template>
            <template v-if="d.devolucoes_almox_pendencias"><br><strong>{{ d.devolucoes_almox_pendencias }} item(ns) não recebido(s) — tratar</strong></template></p>
        </a>
        <a class="acao-card cor-azul" href="/farmacia/nota-consumo">
          <h3>Nota de consumo e RM (AGHU)</h3>
          <div v-if="d.nota_consumo_pendentes" class="numero">{{ d.nota_consumo_pendentes }}</div>
          <p class="rotulo">Uso do dia por paciente.</p>
        </a>
        <a class="acao-card cor-azul" href="/farmacia/conciliacao">
          <h3>Conciliação por sala e prontuário</h3>
          <p class="rotulo">Dispensado × usado × devolvido.</p>
        </a>
        <a class="acao-card cor-azul" href="/farmacia/estoque">
          <h3>Estoque da farmácia</h3>
          <div class="numero">{{ d.estoque_farmacia }}</div>
          <p class="rotulo">unidade(s) em estoque<template v-for="(n, fa) in d.estoque_por_farmacia" :key="fa"> · {{ d.nomes_farmacias[fa] }}: {{ n }}</template></p>
        </a>
        <a class="acao-card cor-azul" href="/consultas/eventos?tipo=devolver_nao_utilizado">
          <h3>Devoluções recebidas</h3>
          <p class="rotulo">Histórico da sala.</p>
        </a>
      </div>
    </section>

  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();

// v18.16: o número grande do cartão é o que motiva o destaque. Antes o cartão ficava
// vermelho por causa de um item não recebido e mostrava um "0" (os envios a conferir).
const aReceber = computed(() => (props.d.envios_a_receber || 0) + (props.d.transferencias_a_receber || 0));
const receberNumero = computed(() => aReceber.value || props.d.envios_pendencias || 0);
</script>
