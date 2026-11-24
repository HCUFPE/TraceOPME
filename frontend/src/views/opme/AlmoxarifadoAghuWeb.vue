<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>{{ robo.titulo }}</h1>
        <p>O robô roda no servidor e a tela do AGHU abre aqui, ocupando a janela inteira. Você faz o login e abre a tela
           certa no AGHU; o robô preenche. <strong>Ele não grava</strong>: no fim você confere e clica em Gravar.</p>
      </div>
      <div class="acoes"><a class="botao secundario" :href="robo.voltar">Voltar</a></div>
    </div>

    <p v-if="!robo.existe" class="aviso erro">Não encontrado.</p>
    <p v-else-if="robo.ja_lancada && !sessao" class="aviso sucesso">{{ robo.ja_lancada }}</p>
    <p v-else-if="d.ocupada_por && !sessao" class="aviso alerta">{{ d.ocupada_por }} está fazendo este lançamento no AGHU agora.</p>

    <div v-else-if="!sessao" class="cartao inicio">
      <h2>Antes de começar</h2>
      <ol><li v-for="(p, n) in robo.passos" :key="n" v-html="p"></li></ol>
      <p class="pequeno suave">A senha que você digita vai direto para o AGHU. O TraceOPME não grava o que é digitado na tela do AGHU.</p>
      <button class="botao botao-grande" :disabled="iniciando || !robo.pode_iniciar" @click="iniciar">{{ iniciando ? 'Iniciando…' : '▶ Iniciar' }}</button>
      <p v-if="erro" class="aviso erro" style="margin-top:.8rem">{{ erro }}</p>
    </div>

    <div v-else-if="!foco" class="cartao">
      <p style="margin:0 0 .6rem">O lançamento está aberto ({{ TITULOS[est.status] || est.status }}).</p>
      <button class="botao" @click="abrirFoco">Abrir a tela do AGHU</button>
    </div>

    <!-- Tela do AGHU ocupando a janela inteira -->
    <div v-if="sessao && foco" ref="caixaFoco" class="foco">
      <div :class="['barra', 'b-' + est.status]">
        <div class="b-nf"><strong>{{ robo.rotulo }}</strong><span class="pilula">{{ TITULOS[est.status] || '…' }}</span></div>
        <div class="b-pergunta">
          <template v-if="est.pergunta">
            <span class="b-txt">{{ est.pergunta.texto }}</span>
            <button v-if="est.pergunta.tipo === 'continuar'" class="botao" @click="responder('')">Pronto, continuar</button>
            <template v-else-if="est.pergunta.opcoes?.length">
              <button v-for="(o, n) in est.pergunta.opcoes" :key="o.valor" :class="['botao', { secundario: n > 0 }]"
                      @click="responder(o.valor)">{{ o.rotulo }}</button>
            </template>
            <form v-else class="b-form" @submit.prevent="responder(resposta)">
              <input v-model="resposta" type="text"><button class="botao">Enviar</button>
            </form>
          </template>
          <span v-else-if="est.resultado" class="b-txt">{{ est.resultado }}</span>
          <span v-else class="b-txt suave-claro">{{ ultimaLinha }}</span>
        </div>
        <div class="b-acoes">
          <button class="botao secundario pequeno" @click="telaCheia">{{ emTelaCheia ? 'Sair da tela cheia' : 'Tela cheia' }}</button>
          <button v-if="ativo" class="botao secundario pequeno" @click="parar">Parar o robô</button>
          <a class="botao secundario pequeno" :href="robo.voltar">{{ ativo ? 'Minimizar' : 'Voltar' }}</a>
        </div>
      </div>

      <div ref="area" :class="['area', { bloqueada: !suaVez }]" @mousedown.prevent="clicar" @mousemove="mover" @wheel.prevent="rolar">
        <img v-if="imagem" ref="img" :src="imagem" alt="Tela do AGHU" draggable="false"
             :style="{ width: est.largura + 'px', maxWidth: '100%', maxHeight: '100%' }">
        <div v-else class="sem-imagem">{{ ativo ? 'Abrindo o AGHU…' : 'Robô encerrado.' }}</div>
        <textarea ref="teclado" class="teclado" autocomplete="off" autocapitalize="off" spellcheck="false"
                  aria-label="Digitar na tela do AGHU" @keydown="tecla" @input="digitou" @paste.prevent="colar"></textarea>
        <div v-if="!suaVez && ativo && imagem" class="faixa">Robô trabalhando — aguarde</div>
      </div>

      <div :class="['rodape', { aberto: logAberto }]">
        <button class="rod-cab" @click="logAberto = !logAberto">
          <strong>Log do robô</strong><span class="rod-ult">{{ ultimaLinha }}</span><span>{{ logAberto ? '▼' : '▲' }}</span>
        </button>
        <div v-show="logAberto" ref="caixaLog" class="log">
          <div v-for="(l, n) in linhas" :key="n" :class="classeLinha(l)">{{ l }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import api from '../../services/api';
import { urlApi } from '../../services/opme';
import { useAuthStore } from '../../stores/auth';
import { useSessaoStore } from '../../stores/sessao';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { postJson, getJson } = useTela();

const TITULOS: Record<string, string> = {
  iniciando: 'Preparando…', trabalhando: 'Robô trabalhando', sua_vez: 'Sua vez',
  concluido: 'Concluído', erro: 'O robô parou', cancelado: 'Robô parado',
};
const robo = computed(() => props.d.robo || {});
const sessao = ref<string>(props.d.sessao || '');
const foco = ref(!!sessao.value);
const est = ref<any>({ status: sessao.value ? 'iniciando' : '', largura: 1366, altura: 768 });
const linhas = ref<string[]>([]);
const imagem = ref('');
const resposta = ref('');
const iniciando = ref(false);
const erro = ref('');
const logAberto = ref(false);
const emTelaCheia = ref(false);
const caixaFoco = ref<HTMLElement | null>(null);
const area = ref<HTMLElement | null>(null);
const img = ref<HTMLImageElement | null>(null);
const caixaLog = ref<HTMLElement | null>(null);
const teclado = ref<HTMLTextAreaElement | null>(null);
const suaVez = computed(() => est.value.status === 'sua_vez');
const ativo = computed(() => !!est.value.ativo || ['iniciando', 'trabalhando', 'sua_vez'].includes(est.value.status));
const ultimaLinha = computed(() => (linhas.value[linhas.value.length - 1] || 'Aguardando o robô…').replace(/^\d\d:\d\d:\d\d\s*/, ''));
let timer: ReturnType<typeof setTimeout> | undefined;
let parado = false;

// Tamanho da tela do AGHU = área livre da janela (1:1, nítido)
function tamanhoDesejado() {
  const larg = area.value?.clientWidth || window.innerWidth;
  const alt = area.value?.clientHeight || (window.innerHeight - 100);
  return { largura: Math.max(1000, Math.min(2560, Math.floor(larg))), altura: Math.max(560, Math.min(1440, Math.floor(alt))) };
}

async function iniciar() {
  iniciando.value = true; erro.value = '';
  try {
    foco.value = true; await nextTick();
    const r: any = await postJson(robo.value.iniciar, tamanhoDesejado());
    if (!r.ok) { erro.value = r.mensagem; foco.value = false; return; }
    sessao.value = r.sessao; linhas.value = []; est.value = { status: 'iniciando', ativo: true, ...tamanhoDesejado() };
    ciclo(); transmitir();
  } catch { erro.value = 'Falha de conexão com o TraceOPME. Tente de novo.'; foco.value = false; } finally { iniciando.value = false; }
}
function abrirFoco() { foco.value = true; nextTick(() => { ciclo(); transmitir(); }); }

// ---- situação, pergunta e log (leve, JSON) ----
async function ciclo() {
  clearTimeout(timer);
  if (parado || !sessao.value) return;
  try {
    const r: any = await getJson(`/almoxarifado/robo-web/${sessao.value}/estado`, { desde: linhas.value.length });
    if (r.ok === false) {
      est.value = { ...est.value, status: 'erro', resultado: r.mensagem, ativo: false };
    } else {
      const eraSuaVez = suaVez.value;
      est.value = r;
      if (r.log?.length) {
        linhas.value.push(...r.log);
        if (logAberto.value) { await nextTick(); if (caixaLog.value) caixaLog.value.scrollTop = caixaLog.value.scrollHeight; }
      }
      if (!eraSuaVez && suaVez.value) { ajustarTamanho(); teclado.value?.focus(); }
    }
  } catch { /* rede oscilou */ }
  if (!ativo.value && est.value.status && est.value.status !== 'iniciando') return;
  timer = setTimeout(ciclo, 700);
}

// ---- tela do AGHU em fluxo contínuo ----
let leitor: ReadableStreamDefaultReader<Uint8Array> | null = null;
let falhasFluxo = 0;
async function transmitir() {
  if (parado || !sessao.value || leitor) return;
  try {
    const cab: Record<string, string> = {};
    const token = useAuthStore().accessToken;
    if (token) cab.Authorization = `Bearer ${token}`;
    try { cab['X-Sessao'] = useSessaoStore().cabecalho(); } catch { /* */ }
    const resp = await fetch(urlApi(`/almoxarifado/robo-web/${sessao.value}/fluxo`), { headers: cab, cache: 'no-store' });
    if (resp.status === 401) { await getJson(`/almoxarifado/robo-web/${sessao.value}/estado`, { desde: 999999 }); throw new Error('401'); }
    if (!resp.ok || !resp.body) throw new Error(String(resp.status));
    leitor = resp.body.getReader();
    falhasFluxo = 0;
    let buf = new Uint8Array(0);
    for (;;) {
      const { value, done } = await leitor.read();
      if (done) break;
      const junto = new Uint8Array(buf.length + value.length); junto.set(buf); junto.set(value, buf.length); buf = junto;
      let ultimo: Uint8Array | null = null;
      while (buf.length >= 4) {
        const n = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3];
        if (buf.length < 4 + n) break;
        if (n > 0) ultimo = buf.slice(4, 4 + n);
        buf = buf.slice(4 + n);
      }
      if (ultimo) mostrar(new Blob([ultimo as BlobPart], { type: "image/jpeg" }));
    }
  } catch { falhasFluxo++; } finally { leitor = null; }
  if (!parado && ativo.value) {
    if (falhasFluxo > 3) { await quadroAvulso(); setTimeout(transmitir, 2000); } else setTimeout(transmitir, 800);
  } else await quadroAvulso();
}
function mostrar(b: Blob) {
  const antiga = imagem.value;
  imagem.value = URL.createObjectURL(b);
  if (antiga) setTimeout(() => URL.revokeObjectURL(antiga), 500);
}
async function quadroAvulso() {
  try {
    const resp = await api.get(urlApi(`/almoxarifado/robo-web/${sessao.value}/tela`), { responseType: 'blob' });
    if (resp.status !== 204 && resp.data?.size) mostrar(resp.data);
  } catch { /* */ }
}

// ---- entrada na tela do AGHU ----
let fila: any[] = [];
let envio: ReturnType<typeof setTimeout> | undefined;
function enfileirar(ev: any) {
  if (!suaVez.value) return;
  fila.push(ev);
  clearTimeout(envio);
  envio = setTimeout(enviar, 40);
}
async function enviar() {
  if (!fila.length) return;
  const eventos = fila; fila = [];
  try { await postJson(`/almoxarifado/robo-web/${sessao.value}/entrada`, { eventos }); } catch { /* */ }
}
function posicao(e: MouseEvent | WheelEvent) {
  const r = (img.value || area.value)!.getBoundingClientRect();
  return { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height };
}
function dentro(p: { x: number; y: number }) { return p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1; }
function clicar(e: MouseEvent) {
  teclado.value?.focus();
  if (!suaVez.value || !imagem.value) return;
  const p = posicao(e);
  if (dentro(p)) enfileirar({ t: 'clique', ...p });
}
let paradoMouse: ReturnType<typeof setTimeout> | undefined;
function mover(e: MouseEvent) {
  if (!suaVez.value || !imagem.value) return;
  clearTimeout(paradoMouse);
  const p = posicao(e);
  if (dentro(p)) paradoMouse = setTimeout(() => enfileirar({ t: 'mover', ...p }), 120);   // menus que abrem ao passar o mouse
}
let ultimaRolagem = 0;
function rolar(e: WheelEvent) {
  if (!suaVez.value) return;
  const agora = Date.now();
  if (agora - ultimaRolagem < 100) return;
  ultimaRolagem = agora;
  enfileirar({ t: 'rolar', ...posicao(e), dy: e.deltaY });
}
const ESPECIAIS = new Set(['Enter', 'Tab', 'Backspace', 'Delete', 'Escape', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown',
  'Home', 'End', 'PageUp', 'PageDown', 'F5']);
function tecla(e: KeyboardEvent) {
  if (ESPECIAIS.has(e.key)) {
    e.preventDefault();
    enfileirar({ t: 'tecla', k: (e.shiftKey && e.key === 'Tab' ? 'Shift+' : '') + e.key });
  } else if ((e.ctrlKey || e.metaKey) && e.key.length === 1 && 'acxz'.includes(e.key.toLowerCase())) {
    e.preventDefault();
    enfileirar({ t: 'tecla', k: 'Control+' + e.key.toLowerCase() });
  }
}
function digitou() {
  const t = teclado.value; if (!t) return;
  const v = t.value; t.value = '';
  if (v) enfileirar({ t: 'texto', v });
}
function colar(e: ClipboardEvent) {
  const v = e.clipboardData?.getData('text') || '';
  if (v) enfileirar({ t: 'texto', v: v.slice(0, 500) });
}

// ---- tamanho / tela cheia ----
let espera: ReturnType<typeof setTimeout> | undefined;
function ajustarTamanho() {
  clearTimeout(espera);
  espera = setTimeout(() => {
    if (!suaVez.value) return;
    const t = tamanhoDesejado();
    if (Math.abs(t.largura - est.value.largura) > 8 || Math.abs(t.altura - est.value.altura) > 8) enfileirar({ t: 'tamanho', ...t });
  }, 400);
}
async function telaCheia() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await caixaFoco.value?.requestFullscreen();
  } catch { /* navegador não deixou */ }
}
function mudouTelaCheia() { emTelaCheia.value = !!document.fullscreenElement; ajustarTamanho(); }
watch(logAberto, async (v) => { if (v) { await nextTick(); if (caixaLog.value) caixaLog.value.scrollTop = caixaLog.value.scrollHeight; } });

async function responder(valor: string) {
  try { await postJson(`/almoxarifado/robo-web/${sessao.value}/responder`, { resposta: valor }); } catch { /* */ }
  resposta.value = '';
  clearTimeout(timer); timer = setTimeout(ciclo, 120);
  teclado.value?.focus();
}
async function parar() {
  if (!window.confirm('Parar o robô? O que ele já incluiu continua na tela do AGHU (não é gravado).')) return;
  try { await postJson(`/almoxarifado/robo-web/${sessao.value}/cancelar`, {}); } catch { /* */ }
}
function classeLinha(l: string) {
  if (/ \? /.test(l)) return 'l-pergunta';
  if (/ERRO|ATENÇÃO|parou|Não achei|não bateu/i.test(l)) return 'l-alerta';
  if (/^\S+ ==/.test(l)) return 'l-material';
  return '';
}

onMounted(() => {
  window.addEventListener('resize', ajustarTamanho);
  document.addEventListener('fullscreenchange', mudouTelaCheia);
  if (sessao.value) { ciclo(); transmitir(); }
});
onBeforeUnmount(() => {
  parado = true; clearTimeout(timer);
  try { leitor?.cancel(); } catch { /* */ }
  window.removeEventListener('resize', ajustarTamanho);
  document.removeEventListener('fullscreenchange', mudouTelaCheia);
  if (imagem.value) URL.revokeObjectURL(imagem.value);
});
</script>

<style scoped>
.inicio ol { margin: .3rem 0 .8rem 1.2rem; line-height: 1.6; }
.botao-grande { font-size: 1.15rem; padding: .85rem 1.8rem; }
.foco { position: fixed; inset: 0; z-index: 1000; background: #15212f; display: flex; flex-direction: column; }
.barra { display: flex; align-items: center; gap: 1rem; padding: .45rem .8rem; background: #fff; border-bottom: 4px solid #8a94a3; min-height: 56px; }
.b-sua_vez { border-bottom-color: #1f6fc4; background: #eef5ff; }
.b-trabalhando, .b-iniciando { border-bottom-color: #b7791f; }
.b-concluido { border-bottom-color: #1e9e5a; background: #e9f7ef; }
.b-erro, .b-cancelado { border-bottom-color: #b3261e; background: #fdecea; }
.b-nf { display: flex; flex-direction: column; gap: .15rem; white-space: nowrap; }
.pilula { font-size: .75rem; font-weight: 700; background: #10233a; color: #fff; border-radius: 999px; padding: .05rem .5rem; align-self: flex-start; }
.b-sua_vez .pilula { background: #1f6fc4; }
.b-pergunta { flex: 1; display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; min-width: 0; }
.b-txt { font-weight: 600; font-size: .98rem; }
.suave-claro { color: #5b6675; font-weight: 400; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.b-form { display: flex; gap: .4rem; }
.b-form input { width: 14rem; }
.b-acoes { display: flex; gap: .4rem; flex-wrap: wrap; justify-content: flex-end; }
.area { flex: 1; min-height: 0; position: relative; display: flex; align-items: center; justify-content: center; overflow: hidden; cursor: default; }
.area.bloqueada { cursor: progress; }
.area img { display: block; object-fit: contain; user-select: none; box-shadow: 0 0 0 1px #2c3a4b; }
.sem-imagem { color: #dfe6ee; font-size: 1.1rem; }
.teclado { position: absolute; left: 0; top: 0; width: 1px; height: 1px; opacity: 0; border: 0; padding: 0; resize: none; }
.faixa { position: absolute; left: 50%; top: .6rem; transform: translateX(-50%); background: rgba(16, 35, 58, .9); color: #fff;
  padding: .35rem .9rem; border-radius: 999px; font-weight: 700; font-size: .9rem; pointer-events: none; }
.rodape { background: #f7f9fb; border-top: 1px solid #d9dee5; }
.rod-cab { width: 100%; display: flex; gap: .8rem; align-items: center; background: none; border: 0; padding: .4rem .8rem; cursor: pointer; text-align: left; font: inherit; }
.rod-ult { flex: 1; color: #5b6675; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: ui-monospace, Consolas, monospace; font-size: .82rem; }
.log { height: 32vh; overflow-y: auto; padding: .3rem .8rem .6rem; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .8rem; line-height: 1.45; }
.log div { white-space: pre-wrap; word-break: break-word; }
.l-pergunta { color: #0c3a67; font-weight: 700; }
.l-alerta { color: #a61b12; font-weight: 600; }
.l-material { color: #0f5b45; font-weight: 700; margin-top: .3rem; }
</style>
