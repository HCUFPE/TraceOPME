<template>
  <div class="opme opme-pagina" ref="raiz" @click="aoClicar" @submit="aoEnviar" @input="sujo = true" @change="sujo = true">
    <!-- Alerta da farmácia: solicitação de OPME em aberto (todas as telas) -->
    <!-- v18.1: sem a unidade da farmácia escolhida, um alerta por farmácia (Bloco / Hemodinâmica). -->
    <div v-if="dados?.pedidos_opme_por_unidade?.length" class="alerta-pedido-unidades nao-imprimir">
      <form v-for="p in dados.pedidos_opme_por_unidade" :key="p.unidade" method="post" action="/farmacia/unidade"
            class="alerta-pedido-opme" style="margin:0;flex:1;min-width:16rem">
        <input type="hidden" name="unidade" :value="p.unidade">
        <input type="hidden" name="proximo" value="/farmacia/solicitacoes">
        <span class="alerta-pedido-ponto"></span>
        <span style="flex:1"><strong>{{ p.rotulo }}: {{ p.n }} solicitação(ões) de OPME em aberto</strong><br>
          <span class="pequeno">É a {{ p.farmacia }}? Clique para atender — daí em diante só aparecem os pedidos dela.</span></span>
        <button class="botao pequeno" data-sem-foco="1">Atender ({{ p.rotulo }})</button>
      </form>
    </div>
    <a v-else-if="dados?.pedidos_opme_abertos" class="alerta-pedido-opme nao-imprimir" href="/farmacia/solicitacoes" data-sem-foco="1">
      <span class="alerta-pedido-ponto"></span>
      <strong>{{ dados.pedidos_opme_abertos }} solicitação(ões) de OPME em aberto<template v-if="dados.pedidos_opme_unidade"> — {{ dados.pedidos_opme_unidade }}</template></strong>
      — a sala pediu material e a farmácia precisa atender. <u>Ver pedidos</u>
    </a>

    <AvisoOpme />

    <div v-if="auto && componente && !falha" class="auto-atualiza nao-imprimir" :class="{ novidade }" @click="novidade = false">
      <span class="ponto"></span>
      <template v-if="novidade"><strong>Houve mudança nesta tela</strong> · </template>
      Atualiza sozinha · {{ atualizadoEm }}<template v-if="sujo"> · <em>pausada enquanto você preenche</em></template>
    </div>

    <div v-if="dados?.sucesso" class="aviso sucesso">{{ dados.sucesso }}</div>
    <div v-if="dados?.erro && !tratarErroNaTela" class="aviso erro">{{ dados.erro }}</div>

    <div v-if="carregando && !componente" class="carregando">Carregando…</div>

    <div v-else-if="falha" class="cartao" style="max-width:560px;margin:3rem auto;text-align:center">
      <div class="numero">{{ falha.codigo }}</div>
      <h1>{{ falha.titulo }}</h1>
      <p class="suave">{{ falha.detalhe }}</p>
      <a class="botao" href="/">Voltar ao painel</a>
    </div>

    <component
      v-else-if="componente"
      :is="componente"
      :key="chaveTela"
      :d="dados"
      :tela="tela"
      @recarregar="recarregar"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref, shallowRef, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AvisoOpme from '../components/opme/AvisoOpme.vue';
import { SEGUNDOS_AUTO, TELAS, TELAS_AUTO } from './opme/telas';
import { useUiStore } from '../stores/ui';
import { useAvisoStore } from '../stores/aviso';
import {
  aplicarEnvelope, baixarArquivo, carregarTela, enviarAcao, mensagemDeErro, rolarAte, rolarTopo, seguir,
  type Envelope,
} from '../services/opme';

const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const avisos = useAvisoStore();

const raiz = ref<HTMLElement | null>(null);
const dados = ref<any>(null);
const tela = ref('');
const componente = shallowRef<any>(null);
const carregando = ref(false);
const falha = ref<{ codigo: number | string; titulo: string; detalhe: string } | null>(null);
const versao = ref(0);
let pedido = 0;

const chaveTela = computed(() => `${tela.value}::${route.path}::${versao.value}`);
// Telas que mostram o "erro" dentro do próprio formulário (sem a faixa do topo).
const tratarErroNaTela = computed(() => !!TELAS[tela.value]?.erroNaTela);

function caminhoAtual() {
  return route.fullPath.split('#')[0];
}

async function definirTela(env: Envelope) {
  const def = TELAS[env.tela || ''];
  if (!def) {
    falha.value = { codigo: 404, titulo: 'Tela não encontrada', detalhe: `A tela “${env.tela}” não existe nesta versão.` };
    componente.value = null;
    return;
  }
  const modulo = await def.componente();
  falha.value = null;
  tela.value = env.tela || '';
  dados.value = env.dados || {};
  componente.value = modulo.default;
  ui.setTitulo(typeof def.titulo === 'function' ? def.titulo(dados.value) : def.titulo);
  versao.value += 1;
  sujo.value = false;
  novidade.value = false;
  marcarHora();
}

// ---------------------------------------------------------------------------
// v18.10: atualização automática das telas de acompanhamento. Só troca os
// dados (a tela não é recriada) e NÃO atualiza se a pessoa está digitando,
// mexeu em algum campo, tem um "detalhe" aberto ou a aba está escondida.
// ---------------------------------------------------------------------------
const sujo = ref(false);
const novidade = ref(false);
const atualizadoEm = ref('');
const auto = computed(() => TELAS_AUTO.has(tela.value));
let timerAuto: number | undefined;
let somNovidade: AudioContext | null = null;

function marcarHora() {
  atualizadoEm.value = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}
function ocupado(): boolean {
  if (document.hidden || sujo.value || carregando.value) return true;
  const ativo = document.activeElement as HTMLElement | null;
  if (ativo && /^(INPUT|TEXTAREA|SELECT)$/.test(ativo.tagName) && (ativo as HTMLInputElement).value) return true;
  if (raiz.value?.querySelector('details[open] input, details[open] textarea, dialog[open]')) return true;
  return !!window.getSelection()?.toString();
}
// "Números" da tela (contadores dos cartões/listas): se aumentarem, houve novidade.
function assinatura(d: any): string {
  const nums: string[] = [];
  const andar = (o: any, k: string, nivel: number) => {
    if (nivel > 2 || o == null) return;
    if (typeof o === 'number') nums.push(`${k}=${o}`);
    else if (Array.isArray(o)) nums.push(`${k}#${o.length}`);
    else if (typeof o === 'object') Object.keys(o).forEach((c) => andar(o[c], `${k}.${c}`, nivel + 1));
  };
  andar(d, '', 0);
  return nums.sort().join('|');
}
function bip() {
  try {
    somNovidade = somNovidade || new AudioContext();
    const o = somNovidade.createOscillator(); const g = somNovidade.createGain();
    o.frequency.value = 880; g.gain.value = 0.05; o.connect(g); g.connect(somNovidade.destination);
    o.start(); o.stop(somNovidade.currentTime + 0.15);
  } catch { /* sem som */ }
}
async function atualizarSozinho() {
  if (!auto.value || ocupado()) return;
  const telaAntes = tela.value;
  const caminho = caminhoAtual();
  try {
    const env = await carregarTela(caminho);
    if (env.redirecionar || env.tela !== telaAntes || caminho !== caminhoAtual() || ocupado()) return;
    const antes = assinatura(dados.value);
    const depois = assinatura(env.dados || {});
    if (env.sessao) aplicarEnvelope({ sessao: env.sessao } as Envelope, false);
    dados.value = env.dados || {};
    marcarHora();
    if (antes !== depois) { novidade.value = true; bip(); }
  } catch { /* tenta de novo no próximo ciclo */ }
}
onMounted(() => { timerAuto = window.setInterval(atualizarSozinho, SEGUNDOS_AUTO * 1000); });
onBeforeUnmount(() => window.clearInterval(timerAuto));

async function carregar() {
  const meu = ++pedido;
  carregando.value = true;
  try {
    const env = await carregarTela(caminhoAtual());
    if (meu !== pedido) return;
    if (env.redirecionar) {
      aplicarEnvelope(env, true);
      const destino = env.redirecionar;
      await router.replace(destino).catch(() => undefined);
      return;
    }
    aplicarEnvelope(env, false);
    await definirTela(env);
    if (route.hash) rolarAte(route.fullPath);
  } catch (e: any) {
    if (meu !== pedido) return;
    const status = e?.response?.status;
    componente.value = null;
    if (status === 401) return; // o interceptor do axios cuida do login
    falha.value = status === 404
      ? { codigo: 404, titulo: 'Página não encontrada', detalhe: 'O endereço acessado não existe ou o item foi removido.' }
      : { codigo: status || '—', titulo: 'Algo deu errado', detalhe: mensagemDeErro(e) };
    ui.setTitulo(falha.value.titulo);
  } finally {
    if (meu === pedido) carregando.value = false;
  }
}

function recarregar() {
  return carregar();
}

/** Resposta de uma ação (formulário) já enviada: segue, recarrega ou redesenha. */
async function tratarResposta(env: Envelope) {
  if (env.redirecionar) {
    aplicarEnvelope(env, true);
    await seguir(env, recarregar);
    return;
  }
  aplicarEnvelope(env, false);
  if (env.tela) {
    await definirTela(env);
    rolarTopo();
  }
}

provide('opmePagina', { recarregar, tratarResposta, dados });

watch(() => [route.path, JSON.stringify(route.query)], () => {
  carregar();
}, { immediate: true });

watch(() => route.hash, (h) => { if (h) rolarAte(route.fullPath); });

// ---------------------------------------------------------------------------
// Navegação e formulários das telas: links internos viram navegação da SPA e
// formulários viram chamadas à API (GET = filtro na URL; POST = ação).
// ---------------------------------------------------------------------------
function aoClicar(evento: MouseEvent) {
  if (evento.defaultPrevented || evento.button !== 0 || evento.metaKey || evento.ctrlKey || evento.shiftKey) return;
  const alvo = (evento.target as HTMLElement)?.closest('a');
  if (!alvo || !raiz.value?.contains(alvo)) return;
  const href = alvo.getAttribute('href') || '';
  if (!href || alvo.target === '_blank' || alvo.hasAttribute('download') && !alvo.hasAttribute('data-baixar')) return;
  if (href.startsWith('#')) {
    evento.preventDefault();
    router.replace({ path: route.path, query: route.query, hash: href }).catch(() => undefined);
    rolarAte(href);
    return;
  }
  if (!href.startsWith('/')) return;
  evento.preventDefault();
  if (alvo.hasAttribute('data-baixar')) {
    baixarArquivo(href, alvo.hasAttribute('data-abrir')).catch((e) => avisos.mostrar({ texto: mensagemDeErro(e), tipo: 'erro' }, false));
    return;
  }
  router.push(href).catch(() => undefined);
}

async function aoEnviar(evento: SubmitEvent) {
  if (evento.defaultPrevented) return;
  const form = evento.target as HTMLFormElement;
  if (!form || form.tagName !== 'FORM' || form.hasAttribute('data-local')) return;
  evento.preventDefault();
  const pergunta = form.dataset.confirmar;
  if (pergunta && !window.confirm(pergunta)) return;
  const metodo = (form.getAttribute('method') || 'get').toLowerCase();
  const acao = form.getAttribute('action') || caminhoAtual().split('?')[0];
  const submitter = (evento.submitter as HTMLButtonElement | null) || null;
  let fd: FormData;
  try {
    fd = submitter ? new FormData(form, submitter) : new FormData(form);
  } catch {
    fd = new FormData(form);
    if (submitter?.name) fd.append(submitter.name, submitter.value);
  }
  if (metodo === 'get') {
    const params = new URLSearchParams();
    fd.forEach((v, k) => { if (typeof v === 'string') params.append(k, v); });
    const qs = params.toString();
    await router.push(qs ? `${acao}?${qs}` : acao).catch(() => undefined);
    return;
  }
  sujo.value = false;
  const botoes = Array.from(form.querySelectorAll('button')) as HTMLButtonElement[];
  const estados = botoes.map((b) => b.disabled);
  botoes.forEach((b) => { b.disabled = true; });
  try {
    const env = await enviarAcao(acao, fd);
    await tratarResposta(env);
  } catch (e: any) {
    avisos.mostrar({ texto: mensagemDeErro(e), tipo: 'erro' }, false);
    rolarTopo();
  } finally {
    botoes.forEach((b, i) => { if (b.isConnected) b.disabled = estados[i]; });
  }
}
</script>

<style scoped>
.auto-atualiza { display: inline-flex; align-items: center; gap: .4rem; font-size: .78rem; opacity: .7;
  margin: 0 0 .6rem; padding: .15rem .6rem; border-radius: 999px; background: var(--cinza-claro, #eef1f4); cursor: default; }
.auto-atualiza .ponto { width: .5rem; height: .5rem; border-radius: 50%; background: #1e9e5a; }
.auto-atualiza.novidade { opacity: 1; background: #fff4d6; border: 1px solid #e0a100; cursor: pointer; }
.auto-atualiza.novidade .ponto { background: #e0a100; animation: pisca 1s infinite; }
@keyframes pisca { 50% { opacity: .2; } }
</style>
