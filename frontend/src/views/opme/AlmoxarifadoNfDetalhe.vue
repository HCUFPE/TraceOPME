<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>NF {{ d.nota.numero_nf }}</h1>
        <p>{{ d.nota.fornecedor }} · importada em {{ f.dataHoraBr(d.nota.data_importacao) }}</p>
        <p class="mono pequeno suave">{{ d.nota.chave_nf }}</p>
      </div>
      <div class="acoes">
        <template v-if="d.concluidos?.length">
          <a v-if="d.mostrar_recebidos" class="botao secundario" :href="`/almoxarifado/nf/${d.nota.chave_nf}`">
            Ocultar os {{ d.concluidos.length }} já recebidos
          </a>
          <a v-else class="botao secundario" :href="`/almoxarifado/nf/${d.nota.chave_nf}?mostrar_recebidos=1`">
            Mostrar os {{ d.concluidos.length }} já recebidos
          </a>
        </template>
        <a class="botao secundario" href="/almoxarifado/nf">Voltar</a>
      </div>
    </div>

    <div class="cartao" style="padding:.8rem 1.25rem">
      <div class="entre">
        <div>
          <strong>{{ d.pendentes.length }}</strong> item(ns) pendente(s) de entrada
          <template v-if="d.concluidos?.length">
            · <span class="suave">{{ d.concluidos.length }} já totalmente recebido(s)
              {{ !d.mostrar_recebidos ? 'e oculto(s) desta lista' : '' }}</span>
          </template>
        </div>
        <span v-if="!d.pendentes.length" class="etiqueta verde">nota totalmente recebida</span>
      </div>
    </div>

    <div v-if="!d.itens?.length" class="cartao">
      <p class="aviso sucesso" style="margin:0">Todos os itens desta nota já foram recebidos. Nada pendente.</p>
    </div>

    <NfItemEntrada v-for="item in d.itens" :key="item.id_item" :item="item" :nota="d.nota" :tipos="d.tipos" />

    <!-- nov/2026: planilha da entrada desta NF para a automação de lançamento no AGHU. -->
    <div class="cartao" id="planilha-aghu" style="margin-top:1.25rem;border-left:5px solid var(--verde, #1b7a4a)">
      <div class="entre" style="gap:1rem;flex-wrap:wrap">
        <div>
          <h2 style="margin:0 0 .3rem">Planilha para lançar no AGHU</h2>
          <p class="pequeno" style="margin:0">Excel com uma linha por material, lote e validade: <strong>código AGHU, código
            consignado (se tiver), lote, validade, fornecedor, marca, quantidade, nº e série da NF e valores</strong> — só o que já deu entrada por esta nota.
            <template v-if="d.pendentes.length"><br><span class="suave">Ainda há {{ d.pendentes.length }} item(ns) pendente(s); a
              planilha traz só o que já entrou.</span></template></p>
        </div>
        <a v-if="d.planilha_aghu" class="botao" data-baixar :href="`/almoxarifado/nf/${d.nota.chave_nf}/planilha-aghu`">
          Baixar Excel ({{ d.planilha_aghu }} linha(s))</a>
        <span v-else class="etiqueta cinza">nenhum item deu entrada ainda</span>
      </div>
    </div>

    <!-- nov/2026: lançamento desta NF no AGHU pelo robô (ou marcação à mão). -->
    <div id="aghu" class="cartao" :style="estiloAghu">
      <div class="entre" style="gap:1rem;flex-wrap:wrap;align-items:flex-start">
        <div style="flex:1 1 380px">
          <h2 style="margin:0 0 .3rem">Lançar no AGHU
            <span :class="['etiqueta', a.status === 'lancada' ? 'verde' : a.status === 'em_lancamento' ? 'azul' : 'amarelo']">{{ a.rotulo }}</span></h2>
          <p v-if="a.status === 'lancada'" class="pequeno" style="margin:0">
            Lançada em {{ f.dataHoraBr(a.lancada_em) }} por {{ a.lancada_por }}<template v-if="a.nr"> · nota de recebimento <strong>{{ a.nr }}</strong></template>.</p>
          <p v-else-if="a.status === 'em_lancamento'" class="pequeno" style="margin:0">
            Robô chamado em {{ f.dataHoraBr(a.iniciado_em) }} por {{ a.iniciado_por }}. Siga a janela preta; no fim ele pergunta
            se a nota foi gravada e atualiza aqui (recarregue a tela).</p>
          <p v-else class="pequeno" style="margin:0">
            <template v-if="a.entrada_concluida"><strong>Entrada concluída no TraceOPME.</strong> </template>
            <template v-else>Ainda há item pendente nesta NF; dá para lançar só o que já entrou. </template>
            O robô abre o navegador no AGHU <strong>neste computador</strong>: você faz o login, abre <em>Gerar Nota de Recebimento
            sem AF</em> e escolhe a NF (cadastrada à mão antes); ele inclui materiais e lotes e para antes de gravar.</p>
          <p v-if="msgRobo" class="pequeno" :style="`margin:.4rem 0 0;color:${erroRobo ? 'var(--vermelho, #b3261e)' : 'inherit'}`">{{ msgRobo }}</p>
          <p v-if="a.status !== 'lancada' && a.instalador_disponivel" class="pequeno suave" style="margin:.4rem 0 0">
            Primeira vez neste computador?
            <a href="/almoxarifado/robo-aghu/instalador" @click.prevent="baixar('/almoxarifado/robo-aghu/instalador')">Baixar o instalador do robô</a>
            — extraia numa pasta fixa e dê dois cliques em <strong>instalar.bat</strong> (uma vez). Se o Windows bloquear o .bat:
            na barra de endereço da pasta digite <strong>cmd</strong>, ENTER, e depois <strong>py instalar.py</strong>.</p>
        </div>
        <div style="display:flex;flex-direction:column;gap:.4rem;align-items:stretch">
          <button v-if="a.status !== 'lancada'" type="button" class="botao" :disabled="!d.planilha_aghu || chamando" style="width:100%"
                  @click="lancarNoAghu">
            {{ chamando ? 'Abrindo…' : a.status === 'em_lancamento' ? 'Abrir o robô de novo' : 'Lançar no AGHU agora' }}</button>
          <details v-if="a.status !== 'lancada'" class="pequeno">
            <summary style="cursor:pointer">Já lancei no AGHU à mão</summary>
            <form method="post" :action="`/almoxarifado/nf/${d.nota.chave_nf}/aghu/marcar`" style="margin:.4rem 0 0;display:flex;gap:.4rem;flex-wrap:wrap">
              <input type="hidden" name="acao" value="lancada">
              <input type="text" name="numero_nr" placeholder="nº da nota de recebimento (opcional)" style="width:15rem">
              <button class="botao secundario pequeno">Marcar como lançada</button>
            </form>
          </details>
          <form v-if="a.status === 'em_lancamento'" method="post" :action="`/almoxarifado/nf/${d.nota.chave_nf}/aghu/marcar`" style="margin:0">
            <input type="hidden" name="acao" value="cancelar">
            <button class="botao secundario pequeno" style="width:100%">Não lancei — voltar para pendente</button>
          </form>
          <form v-if="a.status === 'lancada'" method="post" :action="`/almoxarifado/nf/${d.nota.chave_nf}/aghu/marcar`" style="margin:0"
                data-confirmar="Desfazer a marcação de lançada no AGHU?">
            <input type="hidden" name="acao" value="desfazer">
            <button class="botao secundario pequeno">Desfazer</button>
          </form>
        </div>
      </div>
    </div>

    <details class="cartao" style="margin-top:1.25rem">
      <summary style="cursor:pointer"><strong>Excluir esta nota</strong>
        <span class="suave pequeno">— importou a nota errada ou com dados errados?</span></summary>
      <form v-if="d.exclusao.pode_excluir" method="post" :action="`/almoxarifado/nf/${d.nota.chave_nf}/excluir`" style="margin-top:.8rem"
            :data-confirmar="`Excluir a NF ${d.nota.numero_nf}?${d.exclusao.recebidas ? ` As ${d.exclusao.recebidas} unidade(s) que já entraram saem do estoque.` : ''} Depois é possível importar o XML de novo.`">
        <p class="pequeno">
          <template v-if="d.exclusao.recebidas">
            <strong>{{ d.exclusao.recebidas }} unidade(s) desta nota já deram entrada</strong> e ainda não foram
            movimentadas — a entrada delas será estornada (saem do estoque).
          </template>
          <template v-else>Nenhum item desta nota deu entrada ainda.</template>
          A exclusão fica registrada no histórico com o seu usuário e o motivo.
        </p>
        <div class="campo" style="max-width:480px">
          <label class="obrigatorio" for="motivo-exclusao">Motivo</label>
          <input type="text" id="motivo-exclusao" name="motivo" required
                 placeholder="Ex.: importei o XML errado / código de barras errado">
        </div>
        <button class="botao secundario" style="color:var(--vermelho, #b3261e)">Excluir nota</button>
      </form>
      <p v-else class="aviso erro pequeno" style="margin-top:.8rem">
        Não é possível excluir: {{ d.exclusao.movimentadas }} unidade(s) desta nota já foram movimentadas
        (usadas, em caixa ou com outro registro). Corrija essas unidades pela correção de cadastro.
      </p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import NfItemEntrada from '../../components/opme/NfItemEntrada.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const emit = defineEmits<{ (e: 'recarregar'): void }>();
const { f, postJson, baixar } = useTela();

// nov/2026: o robô fica NESTE computador; o servidor só gera o link traceopme-aghu://
const chamando = ref(false);
const msgRobo = ref('');
const erroRobo = ref(false);
async function lancarNoAghu() {
  if (a.value.status === 'em_lancamento' && !window.confirm('O robô já foi chamado para esta NF. Abrir de novo?')) return;
  chamando.value = true;
  msgRobo.value = '';
  try {
    const r: any = await postJson(`/almoxarifado/nf/${props.d.nota.chave_nf}/aghu/lancar`, { servidor: window.location.origin });
    erroRobo.value = !r.ok;
    msgRobo.value = r.mensagem + (r.ok ? ' Se nada abrir em alguns segundos, o robô não está instalado neste computador (veja o instalador abaixo).' : '');
    if (r.ok && r.link) window.location.href = r.link;
    setTimeout(() => emit('recarregar'), 1500);
  } catch {
    erroRobo.value = true;
    msgRobo.value = 'Falha de conexão com o TraceOPME. Tente de novo.';
  } finally {
    chamando.value = false;
  }
}
const a = computed(() => props.d.aghu || {});
// Entrada concluída e ainda não lançada no AGHU: o cartão fica em destaque.
const estiloAghu = computed(() => {
  const base = 'margin-top:1.25rem;border-left:5px solid ';
  if (a.value.status === 'lancada') return base + '#0f766e;background:#e6f4f1';
  if (a.value.status === 'em_lancamento') return base + '#5b7fa6;background:#edf2f8';
  if (a.value.entrada_concluida) return base + '#b7791f;background:#fbf2e2;box-shadow:0 0 0 3px #f0dcb8';
  return base + '#b7791f';
});
</script>
