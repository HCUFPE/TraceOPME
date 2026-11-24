<template>
  <div class="qg">
    <div class="qg-topo">
      <div>
        <h1>QG da enfermagem</h1>
        <p class="sub">Chamados das salas · atualizado às <strong>{{ p.atualizado_em }}</strong>
          <span class="ao-vivo"></span> <span class="pequeno">próxima em {{ contagem }}s</span></p>
      </div>
      <div class="acoes">
        <div class="seg">
          <a :class="{ ativo: !p.unidade }" href="/qg" data-sem-foco="1">Todas</a>
          <a v-for="(rot, chave) in p.unidades" :key="chave" :class="{ ativo: p.unidade === chave }"
             :href="`/qg?unidade=${encodeURIComponent(String(chave))}`" data-sem-foco="1">{{ rot }}</a>
        </div>
        <button type="button" class="botao secundario" data-sem-foco="1" @click="somLigado = !somLigado">
          {{ somLigado ? '🔔 Som ligado' : '🔕 Som desligado' }}</button>
      </div>
    </div>

    <div v-if="mensagem.texto" :class="['aviso', mensagem.ok ? 'sucesso' : 'erro']">{{ mensagem.texto }}</div>

    <div class="qg-kpis">
      <div class="kpi k-verm" :class="{ pulsa: p.resumo.aguardando }"><div class="n">{{ p.resumo.aguardando }}</div><div class="r">aguardando direcionar</div></div>
      <div class="kpi k-azul"><div class="n">{{ p.resumo.a_caminho }}</div><div class="r">a caminho</div></div>
      <div class="kpi k-verde"><div class="n">{{ p.resumo.atendidos_hoje }}</div><div class="r">atendidos hoje</div></div>
      <div class="kpi k-cinza"><div class="n">{{ p.resumo.tempo_medio ?? '—' }}<small v-if="p.resumo.tempo_medio != null"> min</small></div><div class="r">tempo médio (chamado → atendido)</div></div>
    </div>

    <datalist id="equipe-qg"><option v-for="n in nomes" :key="n" :value="n" /></datalist>

    <div class="colunas">
      <section class="col col-aguardando">
        <h2>Aguardando ({{ p.aguardando.length }})</h2>
        <p v-if="!p.aguardando.length" class="vazio">Nenhum chamado esperando.</p>
        <article v-for="c in p.aguardando" :key="c.id_chamado" :class="['ch', 'tp-' + c.tipo, { novo: novos.has(c.id_chamado), atrasado: c.espera_min >= 10 }]">
          <div class="ch-cab"><span class="ic">{{ c.icone }}</span>
            <div><strong>{{ c.tipo_rotulo }}</strong> → <span class="sala">{{ curto(c.unidade) }} · Sala {{ c.sala }}</span></div>
            <span class="tempo">{{ c.espera_min }} min</span></div>
          <div class="motivo">{{ c.motivo || '—' }}<template v-if="c.observacao"> — <em>{{ c.observacao }}</em></template></div>
          <div class="pequeno suave">chamado às {{ hora(c.criado_em) }} por {{ c.criado_por }}</div>
          <form class="direcionar" @submit.prevent="direcionar(c)">
            <input v-model="responsavel[c.id_chamado]" list="equipe-qg" :placeholder="c.tipo === 'maqueiro' ? 'nome do maqueiro' : 'nome / equipe da limpeza'"
                   :aria-label="'Quem vai: ' + c.tipo_rotulo" required>
            <button class="botao">Direcionar</button>
          </form>
          <div class="ch-acoes">
            <button type="button" class="link" @click="atender(c)">já resolvido</button>
            <button type="button" class="link" @click="cancelar(c)">cancelar</button>
          </div>
        </article>
      </section>

      <section class="col col-caminho">
        <h2>A caminho ({{ p.a_caminho.length }})</h2>
        <p v-if="!p.a_caminho.length" class="vazio">Ninguém a caminho.</p>
        <article v-for="c in p.a_caminho" :key="c.id_chamado" :class="['ch', 'tp-' + c.tipo]">
          <div class="ch-cab"><span class="ic">{{ c.icone }}</span>
            <div><strong>{{ c.tipo_rotulo }}</strong> → <span class="sala">{{ curto(c.unidade) }} · Sala {{ c.sala }}</span></div>
            <span class="tempo">{{ c.a_caminho_min }} min</span></div>
          <div class="motivo">{{ c.motivo || '—' }}<template v-if="c.observacao"> — <em>{{ c.observacao }}</em></template></div>
          <div class="quem">👤 <strong>{{ c.responsavel }}</strong> <span class="pequeno suave">desde {{ hora(c.direcionado_em) }}</span></div>
          <div class="ch-acoes">
            <button type="button" class="botao" @click="atender(c)">✓ Atendido</button>
            <button type="button" class="link" @click="trocar(c)">trocar pessoa</button>
            <button type="button" class="link" @click="cancelar(c)">cancelar</button>
          </div>
        </article>
      </section>

      <section class="col col-feitos">
        <h2>Hoje ({{ p.finalizados.length }})</h2>
        <p v-if="!p.finalizados.length" class="vazio">Nada finalizado hoje.</p>
        <article v-for="c in p.finalizados" :key="c.id_chamado" :class="['ch', 'mini', 'st-' + c.status]">
          <span class="ic">{{ c.icone }}</span>
          <div style="flex:1"><strong>{{ curto(c.unidade) }} · Sala {{ c.sala }}</strong> <span class="pequeno">{{ c.motivo }}</span><br>
            <span class="pequeno suave"><template v-if="c.status === 'atendido'">{{ hora(c.criado_em) }} → {{ hora(c.atendido_em) }}
              ({{ c.tempo_total_min }} min)<template v-if="c.responsavel"> · {{ c.responsavel }}</template></template>
              <template v-else>cancelado às {{ hora(c.cancelado_em) }}</template></span></div>
        </article>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { getJson, postJson } = useTela();
const p = ref<any>(props.d);
watch(() => props.d, (v) => { p.value = v; });

const contagem = ref(15);
const somLigado = ref(true);
const responsavel = reactive<Record<string, string>>({});
const mensagem = reactive({ ok: true, texto: '' });
const novos = ref(new Set<string>());
const CURTO: Record<string, string> = { 'BLOCO CIRURGICO': 'Bloco', 'HEMODINAMICA - PDT': 'Hemodinâmica' };
const curto = (u: string) => CURTO[u] || u;
const hora = (v: string) => String(v || '').slice(11, 16);
let relogio: number | undefined;

// Nomes já usados neste computador (sugestão no campo "quem vai").
const nomes = ref<string[]>([]);
try { nomes.value = JSON.parse(localStorage.getItem('qg_nomes') || '[]'); } catch { nomes.value = []; }
function lembrar(nome: string) {
  nomes.value = [nome, ...nomes.value.filter((n) => n.toLowerCase() !== nome.toLowerCase())].slice(0, 30);
  try { localStorage.setItem('qg_nomes', JSON.stringify(nomes.value)); } catch { /* opcional */ }
}

function bip() {
  if (!somLigado.value) return;
  try {
    const c = new (window.AudioContext || (window as any).webkitAudioContext)();
    [0, 0.22].forEach((t) => {
      const o = c.createOscillator(); o.frequency.value = 880; o.connect(c.destination);
      o.start(c.currentTime + t); o.stop(c.currentTime + t + 0.14);
    });
  } catch { /* som é acessório */ }
}

async function atualizar() {
  try {
    const antes = new Set<string>(p.value.aguardando.map((c: any) => c.id_chamado));
    const novo: any = await getJson('/qg/dados', { unidade: p.value.unidade || '' });
    const chegaram = novo.aguardando.filter((c: any) => !antes.has(c.id_chamado)).map((c: any) => c.id_chamado);
    p.value = novo;
    if (chegaram.length) {
      novos.value = new Set(chegaram);
      bip();
      window.setTimeout(() => { novos.value = new Set(); }, 8000);
    }
  } catch { /* tenta no próximo ciclo */ }
}
function tic() { contagem.value -= 1; if (contagem.value <= 0) { contagem.value = 15; atualizar(); } }

async function acao(c: any, nome: string, corpo: any = {}) {
  const r: any = await postJson(`/qg/chamado/${c.id_chamado}/${nome}`, corpo);
  mensagem.ok = !!r.ok; mensagem.texto = r.mensagem || '';
  window.setTimeout(() => { mensagem.texto = ''; }, 4000);
  contagem.value = 15;
  await atualizar();
}
async function direcionar(c: any) {
  const nome = (responsavel[c.id_chamado] || '').trim();
  if (!nome) return;
  lembrar(nome);
  await acao(c, 'direcionar', { responsavel: nome });
}
async function trocar(c: any) {
  const nome = (window.prompt('Quem vai agora?', c.responsavel || '') || '').trim();
  if (nome) { lembrar(nome); await acao(c, 'direcionar', { responsavel: nome }); }
}
const atender = (c: any) => acao(c, 'atender');
async function cancelar(c: any) {
  const motivo = window.prompt('Cancelar o chamado? Escreva o motivo (opcional):', '');
  if (motivo !== null) await acao(c, 'cancelar', { motivo });
}

onMounted(() => { relogio = window.setInterval(tic, 1000); });
onBeforeUnmount(() => window.clearInterval(relogio));
</script>

<style scoped>
.qg-topo { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
.qg-topo h1 { margin: 0; }
.sub { margin: .2rem 0 0; color: var(--texto-suave, #5b6675); }
.acoes { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }
.ao-vivo { display: inline-block; width: .6rem; height: .6rem; border-radius: 50%; background: #1e9e5a; margin-left: .3rem; vertical-align: middle; animation: vivo 1.6s infinite; }
@keyframes vivo { 0% { box-shadow: 0 0 0 0 rgba(30,158,90,.6); } 100% { box-shadow: 0 0 0 .6rem rgba(30,158,90,0); } }
.seg { display: inline-flex; border: 1px solid var(--borda, #d9dee5); border-radius: 10px; overflow: hidden; }
.seg a { padding: .55rem .9rem; text-decoration: none; color: inherit; font-weight: 600; background: #fff; }
.seg a + a { border-left: 1px solid var(--borda, #d9dee5); }
.seg a.ativo { background: var(--azul, #0c3a67); color: #fff; }
.qg-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: .7rem; margin-bottom: 1rem; }
.kpi { background: #fff; border: 1px solid var(--borda, #d9dee5); border-radius: 12px; padding: .8rem 1rem; border-top: 5px solid; }
.kpi .n { font-size: 2.1rem; font-weight: 800; line-height: 1; } .kpi .n small { font-size: 1rem; }
.kpi .r { font-size: .85rem; margin-top: .3rem; opacity: .8; }
.k-verm { border-top-color: #c62828; } .k-azul { border-top-color: #1f6fc4; } .k-verde { border-top-color: #1e9e5a; } .k-cinza { border-top-color: #8a94a3; }
.kpi.pulsa { animation: pulsa 1.4s infinite; } @keyframes pulsa { 50% { box-shadow: 0 0 0 5px rgba(198,40,40,.25); } }
.colunas { display: grid; grid-template-columns: 1.15fr 1fr .85fr; gap: 1rem; align-items: start; }
@media (max-width: 1000px) { .colunas { grid-template-columns: 1fr; } }
.col { background: #f4f6f9; border-radius: 14px; padding: .8rem; min-height: 12rem; }
.col h2 { margin: 0 0 .7rem; font-size: 1.05rem; }
.col-aguardando { background: #fff3f1; } .col-caminho { background: #eef5ff; }
.ch { background: #fff; border: 1px solid var(--borda, #d9dee5); border-radius: 12px; padding: .75rem .85rem; margin-bottom: .7rem;
  border-left: 6px solid var(--cor-tp, #8a94a3); display: flex; flex-direction: column; gap: .35rem; }
.tp-maqueiro { --cor-tp: #1f6fc4; } .tp-limpeza { --cor-tp: #0f9fb0; }
.ch.novo { animation: chegou 1s ease-in-out 4; }
@keyframes chegou { 50% { box-shadow: 0 0 0 5px rgba(198,40,40,.35); transform: scale(1.01); } }
.ch.atrasado .tempo { background: #c62828; color: #fff; }
.ch-cab { display: flex; align-items: center; gap: .6rem; }
.ch-cab .ic, .mini .ic { font-size: 1.6rem; }
.ch-cab > div { flex: 1; font-size: 1.05rem; }
.sala { font-weight: 800; }
.tempo { font-weight: 700; padding: .15rem .55rem; border-radius: 999px; background: #e9edf2; font-size: .85rem; white-space: nowrap; }
.motivo { font-size: .95rem; }
.direcionar { display: flex; gap: .4rem; margin: .2rem 0 0; }
.direcionar input { flex: 1; min-width: 0; }
.ch-acoes { display: flex; gap: .8rem; align-items: center; flex-wrap: wrap; }
.link { all: unset; cursor: pointer; color: var(--azul, #0c3a67); text-decoration: underline; font-size: .88rem; }
.quem { font-size: 1rem; }
.ch.mini { flex-direction: row; align-items: center; gap: .6rem; padding: .5rem .7rem; border-left-width: 4px; }
.st-atendido { --cor-tp: #1e9e5a; } .st-cancelado { --cor-tp: #8a94a3; opacity: .7; }
@media (prefers-reduced-motion: reduce) { .ch.novo, .kpi.pulsa, .ao-vivo { animation: none; } }
</style>
