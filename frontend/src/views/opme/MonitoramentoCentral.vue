<template>
  <div ref="raiz" :class="['central', { tv }]">
    <!-- Cabeçalho -->
    <div class="central-topo">
      <div>
        <h1>Central das salas</h1>
        <p class="sub">
          <template v-if="p.hoje">Ao vivo · atualizado às <strong>{{ p.atualizado_em }}</strong>
            <span class="ao-vivo" :class="{ parado: !autoAtualizar }"></span>
            <span v-if="autoAtualizar" class="pequeno"> próxima em {{ contagem }}s</span></template>
          <template v-else>Dia {{ f.dataBr(p.data) }} · visão do histórico</template>
        </p>
      </div>
      <div class="central-acoes">
        <div class="seg">
          <a :class="{ ativo: !p.unidade }" :href="link('todas', p.data)" data-sem-foco="1">Todas</a>
          <a v-for="(rot, chave) in p.unidades" :key="chave" :class="{ ativo: p.unidade === chave }"
             :href="link(String(chave), p.data)" data-sem-foco="1">{{ rot }}</a>
        </div>
        <input type="date" :value="p.data" class="data" data-sem-foco="1" @change="trocarData">
        <button type="button" class="botao secundario" data-sem-foco="1" @click="alternarAuto">
          {{ autoAtualizar ? '⏸ Pausar' : '▶ Ao vivo' }}</button>
        <button type="button" class="botao" data-sem-foco="1" @click="alternarTv">{{ tv ? '✕ Sair do modo TV' : '🖥 Modo TV' }}</button>
      </div>
    </div>

    <!-- Números do momento -->
    <div class="kpis">
      <div class="kpi k-azul"><div class="n">{{ p.resumo.em_andamento }}</div><div class="r">sala(s) em andamento</div></div>
      <div class="kpi k-amarelo" :class="{ pulsa: p.resumo.pedidos_abertos }"><div class="n">{{ p.resumo.pedidos_abertos }}</div><div class="r">pedido(s) de OPME em aberto</div></div>
      <div class="kpi k-verde"><div class="n">{{ p.resumo.itens_bipados }}</div><div class="r">item(ns) bipado(s) no dia</div></div>
      <div class="kpi k-roxo"><div class="n">{{ p.resumo.conferencia_farmacia }}</div><div class="r">em conferência na farmácia</div></div>
      <div class="kpi k-cinza"><div class="n">{{ p.resumo.finalizados }}<small>/{{ p.resumo.procedimentos }}</small></div><div class="r">procedimentos finalizados pela sala</div></div>
      <div class="kpi k-ciano"><div class="n">{{ p.resumo.chamados }}</div><div class="r">chamado(s) de maqueiro / limpeza</div></div>
      <div class="kpi k-vermelho" :class="{ pulsa: p.resumo.com_alerta }"><div class="n">{{ p.resumo.com_alerta }}</div><div class="r">sala(s) com alerta</div></div>
    </div>

    <div class="legenda">
      <span v-for="l in p.legenda" :key="l.etapa" class="leg"><i :class="'c-' + l.cor"></i>{{ l.rotulo }}</span>
      <span class="leg"><i class="c-alerta"></i>Alerta</span>
      <span class="leg etapas-leg">Etapas da bolinha:
        <template v-for="(e, i) in p.etapas" :key="e.chave"><b>{{ i + 1 }}</b> {{ e.rotulo }}<template v-if="i < p.etapas.length - 1"> · </template></template>
        · <b>–</b> não passou pela etapa</span>
    </div>

    <!-- As salas -->
    <template v-for="(grupo, un) in porUnidade" :key="un">
      <h2 v-if="Object.keys(porUnidade).length > 1" class="titulo-unidade">{{ p.unidades[un] }}</h2>
      <div class="grade-salas">
        <button v-for="s in grupo" :key="s.chave" type="button" data-sem-foco="1"
                :class="['sala', 'c-' + s.cor, { alerta: s.alertas.some((a: any) => a.atrasado), pulsa: s.alertas.some((a: any) => a.tipo === 'pedido'), escolhida: escolhida?.chave === s.chave }]"
                @click="abrir(s)">
          <div class="sala-topo">
            <div class="sala-num"><small>SALA</small>{{ s.sala }}</div>
            <div class="sala-sit">{{ s.situacao }}</div>
          </div>
          <template v-if="s.atual">
            <div class="paciente">
              <strong>{{ s.atual.paciente || 'Paciente' }}</strong>
              <span class="mono"> · {{ s.atual.prontuario }}</span>
            </div>
            <div class="espec">{{ s.atual.especialidade }}<template v-if="s.atual.hora_agendada"> · agendado {{ s.atual.hora_agendada }}</template></div>
            <ol class="passos">
              <li v-for="(e, i) in p.etapas" :key="e.chave" :class="passo(s.atual, i)"
                  :title="e.rotulo + (s.atual.horas[e.chave] ? ' às ' + s.atual.horas[e.chave] : passo(s.atual, i) === 'pulado' ? ' (não passou por esta etapa)' : '')">
                <span class="bola">{{ passo(s.atual, i) === 'feito' ? '✓' : passo(s.atual, i) === 'pulado' ? '–' : i + 1 }}</span>
                <span class="hora">{{ s.atual.horas[e.chave] || '' }}</span>
              </li>
            </ol>
            <div class="info">
              <span v-if="s.atual.aberta_ha">⏱ aberta há <strong>{{ s.atual.aberta_ha }}</strong></span>
              <span v-else-if="s.atual.duracao">⏱ durou {{ s.atual.duracao }}</span>
              <span v-if="s.atual.bips">▮▮ <strong>{{ s.atual.bips }}</strong> bipado(s)<template v-if="s.atual.ultimo_bip"> · último {{ s.atual.ultimo_bip }}</template></span>
              <span v-if="s.atual.solicitacao?.faltando">📋 faltam {{ s.atual.solicitacao.faltando }} de {{ s.atual.solicitacao.linhas }} do pedido</span>
            </div>
          </template>
          <div v-else class="vazia">{{ s.na_farmacia.length ? 'Pronta para o próximo paciente.' : 'Nenhum procedimento neste dia.' }}</div>
          <ul v-if="s.alertas.length" class="avisos">
            <li v-for="(a, i) in s.alertas.slice(0, 2)" :key="i" :class="{ leve: !a.atrasado }">{{ a.tipo === 'pedido' ? '📋' : '⚠' }} {{ a.texto }}</li>
            <li v-if="s.alertas.length > 2">+{{ s.alertas.length - 2 }} alerta(s)</li>
          </ul>
          <!-- v18.3: chamados abertos desta sala -->
          <div v-if="s.chamados.length" class="chamados-sala">
            <span v-for="c in s.chamados" :key="c.id_chamado" :class="['chip-ch', 'ch-' + c.status]">
              {{ c.icone }} {{ c.tipo_rotulo }}:
              <template v-if="c.status === 'aberto'">chamado há {{ c.espera_min }} min</template>
              <template v-else>{{ c.responsavel }} a caminho</template>
            </span>
          </div>
          <!-- v18.3: o que já saiu da sala e a farmácia ainda confere (a sala pode já ter outro paciente) -->
          <div v-if="s.na_farmacia.length" class="na-farmacia">
            <div v-for="pr in s.na_farmacia" :key="pr.id_atendimento">
              <i class="pt c-roxo"></i> <strong>{{ pr.paciente || pr.prontuario }}</strong>
              <span class="pequeno"> · {{ pr.etapa === 'conferido' ? 'conferido, falta concluir' : 'conferência da farmácia' }} desde {{ pr.farmacia_desde }} ({{ pr.farmacia_ha }})</span>
            </div>
          </div>
          <div v-if="s.procedimentos.length" class="fila" :title="`${s.contagem.total} procedimento(s) no dia`">
            <i v-for="pr in s.procedimentos" :key="pr.id_atendimento" :class="['pt', 'c-' + pr.cor, { atual: pr.id_atendimento === s.atual?.id_atendimento }]"></i>
            <span>{{ s.contagem.feitos }}/{{ s.contagem.total - s.contagem.cancelados }} no dia</span>
          </div>
        </button>
      </div>
    </template>

    <!-- Linha do tempo do dia -->
    <div class="cartao gantt-cartao">
      <h2>Linha do tempo do dia</h2>
      <p class="pequeno suave" style="margin-top:0">Cada barra é um procedimento: da 1ª ação da sala até a finalização.
        Os tracinhos são os bips no paciente; o losango vazado é o horário agendado que ainda não começou.</p>
      <div class="gantt">
        <div class="g-eixo">
          <div class="g-rot"></div>
          <div class="g-trilha">
            <span v-for="h in horas" :key="h" class="g-h" :style="{ left: pos(h * 60) + '%' }">{{ String(h).padStart(2, '0') }}h</span>
          </div>
        </div>
        <div v-for="s in p.salas" :key="s.chave" class="g-linha" @click="abrir(s)">
          <div class="g-rot">{{ Object.keys(porUnidade).length > 1 ? curto(s.unidade) + ' ' : 'Sala ' }}{{ s.sala }}</div>
          <div class="g-trilha">
            <span v-for="h in horas" :key="h" class="g-grade" :style="{ left: pos(h * 60) + '%' }"></span>
            <span v-if="p.hoje" class="g-agora" :style="{ left: pos(agoraMin) + '%' }"></span>
            <template v-for="pr in s.procedimentos" :key="pr.id_atendimento">
              <span v-if="pr.inicio_iso" :class="['g-barra', 'c-' + pr.cor]"
                    :style="barra(pr)" :title="`${pr.paciente} · ${pr.situacao}`"></span>
              <span v-else-if="pr.hora_agendada && pr.etapa === 'agendado'" class="g-agendado"
                    :style="{ left: pos(minDe(pr.hora_agendada)) + '%' }" :title="`Agendado ${pr.hora_agendada} · ${pr.paciente}`"></span>
              <span v-for="(b, i) in pr.bips_horas" :key="pr.id_atendimento + i" class="g-bip" :style="{ left: pos(minDe(b)) + '%' }"></span>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- Painel lateral da sala -->
    <div v-if="escolhida" class="fundo" @click="escolhida = null"></div>
    <aside v-if="escolhida" class="lateral">
      <div class="lat-topo" :class="'c-' + escolhida.cor">
        <div><small>{{ escolhida.unidade_rotulo }}</small><h2>Sala {{ escolhida.sala }}</h2><div>{{ escolhida.situacao }}</div></div>
        <button type="button" class="fechar" data-sem-foco="1" @click="escolhida = null">✕</button>
      </div>
      <div class="lat-corpo">
        <p v-if="!escolhida.procedimentos.length" class="vazio">Nenhum procedimento neste dia.</p>
        <div v-for="pr in escolhida.procedimentos" :key="pr.id_atendimento"
             :class="['lat-proc', { aberto: aberto === pr.id_atendimento }]">
          <button type="button" class="lat-cab" data-sem-foco="1" @click="verLinha(pr)">
            <i :class="['pt', 'c-' + pr.cor]"></i>
            <span style="flex:1;text-align:left"><strong>{{ pr.paciente || 'Paciente' }}</strong> <span class="mono pequeno">{{ pr.prontuario }}</span><br>
              <span class="pequeno suave">{{ pr.especialidade }}<template v-if="pr.hora_agendada"> · {{ pr.hora_agendada }}</template> · {{ pr.situacao }}</span></span>
            <span class="pequeno">{{ aberto === pr.id_atendimento ? '▲' : '▼' }}</span>
          </button>
          <div v-if="aberto === pr.id_atendimento" class="lat-det">
            <div class="etapas-lista">
              <div v-for="(e, i) in p.etapas" :key="e.chave" :class="passo(pr, i)">
                <span class="bola">{{ passo(pr, i) === 'feito' ? '✓' : '' }}</span> {{ e.rotulo }}
                <strong style="margin-left:auto">{{ pr.horas[e.chave] || (passo(pr, i) === 'pulado' ? 'não passou' : '—') }}</strong>
              </div>
            </div>
            <ul v-if="pr.alertas.length" class="avisos" style="margin:.6rem 0">
              <li v-for="(a, i) in pr.alertas" :key="i">⚠ {{ a.texto }}</li>
            </ul>
            <h3>O que aconteceu</h3>
            <p v-if="carregandoLinha" class="pequeno suave">Carregando…</p>
            <ol v-else-if="linha.length" class="tempo">
              <li v-for="(ev, i) in linha" :key="i" :class="{ ruim: ev.tipo === 'avaria_sinalizada' || ev.tipo === 'atendimento_cancelado' }">
                <span class="th">{{ ev.hora }}</span>
                <div><strong>{{ ev.rotulo }}<template v-if="ev.qtd > 1"> — {{ ev.qtd }} itens</template></strong>
                  <div v-if="ev.materiais.length" class="pequeno suave">{{ ev.materiais.join(' · ') }}<template v-if="ev.qtd > ev.materiais.length"> …</template></div>
                  <div v-if="ev.detalhe" class="pequeno">{{ ev.detalhe }}</div>
                  <div class="pequeno suave">{{ ev.usuario }}</div></div>
              </li>
            </ol>
            <p v-else class="pequeno suave">Nada registrado ainda.</p>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, getJson } = useTela();

const p = ref<any>(props.d);
watch(() => props.d, (v) => { p.value = v; });

const raiz = ref<HTMLElement | null>(null);
const tv = ref(false);
const autoAtualizar = ref(true);
const contagem = ref(30);
const escolhida = ref<any>(null);
const aberto = ref('');
const linha = ref<any[]>([]);
const carregandoLinha = ref(false);
let relogio: number | undefined;

const CURTO: Record<string, string> = { 'BLOCO CIRURGICO': 'Bloco', 'HEMODINAMICA - PDT': 'Hemo' };
const curto = (u: string) => CURTO[u] || u;
const link = (unidade: string, data: string) => `/monitoramento?unidade=${encodeURIComponent(unidade)}&data=${data}`;

// Etapa feita = tem hora registrada. Etapa que ficou para trás sem hora (ex.:
// bipou sem pedir OPME) = "pulado". "agora" = a próxima que falta.
function passo(pr: any, i: number): string {
  const chave = p.value.etapas[i].chave;
  if (pr.horas[chave]) return 'feito';
  const ultimaFeita = p.value.etapas.reduce((m: number, e: any, j: number) => (pr.horas[e.chave] ? j : m), -1);
  if (i < ultimaFeita) return 'pulado';
  if (i === ultimaFeita + 1 && !['agendado', 'concluido', 'cancelado'].includes(pr.etapa)) return 'agora';
  return '';
}

const porUnidade = computed(() => {
  const g: Record<string, any[]> = {};
  for (const s of p.value.salas || []) (g[s.unidade] ||= []).push(s);
  return g;
});

// ---- linha do tempo: janela de horas do dia (06h–20h, ou maior se precisar)
function minDe(hhmm: string): number {
  const [h, m] = String(hhmm || '').split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
}
function minIso(iso: string): number { return iso ? minDe(iso.slice(11, 16)) : 0; }
const agoraMin = computed(() => minIso(p.value.agora_iso));
const janela = computed(() => {
  let ini = 6 * 60, fim = 20 * 60;
  for (const s of p.value.salas || []) for (const pr of s.procedimentos) {
    for (const v of [minIso(pr.inicio_iso), pr.fim_iso ? minIso(pr.fim_iso) : 0, pr.hora_agendada ? minDe(pr.hora_agendada) : 0]) {
      if (v) { ini = Math.min(ini, Math.floor(v / 60) * 60); fim = Math.max(fim, Math.ceil(v / 60) * 60); }
    }
  }
  return { ini, fim };
});
const horas = computed(() => {
  const r: number[] = [];
  for (let h = janela.value.ini / 60; h <= janela.value.fim / 60; h += 1) r.push(h);
  return r;
});
const pos = (min: number) => Math.max(0, Math.min(100, ((min - janela.value.ini) / (janela.value.fim - janela.value.ini)) * 100));
function barra(pr: any) {
  const a = minIso(pr.inicio_iso);
  const b = pr.fim_iso ? minIso(pr.fim_iso) : (p.value.hoje ? agoraMin.value : a + 15);
  return { left: pos(a) + '%', width: Math.max(0.6, pos(Math.max(b, a + 5)) - pos(a)) + '%' };
}

// ---- atualização automática
async function atualizar() {
  try {
    const novo = await getJson('/monitoramento/dados', { unidade: p.value.unidade || 'todas', data: p.value.data });
    p.value = novo;
    if (escolhida.value) escolhida.value = novo.salas.find((s: any) => s.chave === escolhida.value.chave) || null;
    if (aberto.value) await carregarLinha(aberto.value);
  } catch { /* tenta de novo no próximo ciclo */ }
}
function tic() {
  if (!autoAtualizar.value || !p.value.hoje) return;
  contagem.value -= 1;
  if (contagem.value <= 0) { contagem.value = 30; atualizar(); }
}
function alternarAuto() { autoAtualizar.value = !autoAtualizar.value; contagem.value = 30; if (autoAtualizar.value) atualizar(); }
function trocarData(ev: Event) {
  const v = (ev.target as HTMLInputElement).value;
  if (v) window.location.assign(link(p.value.unidade || 'todas', v));
}
async function alternarTv() {
  tv.value = !tv.value;
  try {
    if (tv.value && raiz.value?.requestFullscreen) await raiz.value.requestFullscreen();
    else if (!tv.value && document.fullscreenElement) await document.exitFullscreen();
  } catch { /* tela cheia é opcional */ }
}
function saiuTelaCheia() { if (!document.fullscreenElement) tv.value = false; }

// ---- painel lateral
async function carregarLinha(id: string) {
  try {
    const r: any = await getJson(`/monitoramento/procedimento/${id}`);
    if (aberto.value === id) linha.value = r.eventos || [];
  } catch { linha.value = []; }
}
function abrir(s: any) {
  escolhida.value = s;
  const alvo = s.atual || s.procedimentos[0];
  if (alvo) verLinha(alvo, true); else aberto.value = '';
}
async function verLinha(pr: any, forcar = false) {
  if (aberto.value === pr.id_atendimento && !forcar) { aberto.value = ''; return; }
  aberto.value = pr.id_atendimento;
  linha.value = [];
  carregandoLinha.value = true;
  await carregarLinha(pr.id_atendimento);
  carregandoLinha.value = false;
}

onMounted(() => {
  relogio = window.setInterval(tic, 1000);
  document.addEventListener('fullscreenchange', saiuTelaCheia);
});
onBeforeUnmount(() => {
  window.clearInterval(relogio);
  document.removeEventListener('fullscreenchange', saiuTelaCheia);
});
</script>

<style scoped>
.central { --cinza: #8a94a3; --azul-claro: #7fb2e5; --azul-st: #1f6fc4; --amarelo-st: #e0a100; --ciano: #0f9fb0;
  --verde-st: #1e9e5a; --roxo: #7a4fc4; --verde-escuro: #2f6b45; --vermelho-st: #c62828; }
.central.tv { position: fixed; inset: 0; z-index: 9999; overflow: auto; background: #0e1726; color: #e9eef5; padding: 1.4rem 1.8rem; }
.central.tv .cartao, .central.tv .kpi { background: #16233a; border-color: #23344f; color: #e9eef5; }
.central.tv h1, .central.tv h2 { color: #fff; }
.central.tv .sub, .central.tv .suave { color: #a9b6c8; }
.central.tv .grade-salas { grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }

.central-topo { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
.central-topo h1 { margin: 0; }
.sub { margin: .2rem 0 0; color: var(--texto-suave, #5b6675); }
.ao-vivo { display: inline-block; width: .6rem; height: .6rem; border-radius: 50%; background: #1e9e5a; margin-left: .35rem;
  box-shadow: 0 0 0 0 rgba(30, 158, 90, .6); animation: vivo 1.6s infinite; vertical-align: middle; }
.ao-vivo.parado { background: #8a94a3; animation: none; }
@keyframes vivo { 0% { box-shadow: 0 0 0 0 rgba(30,158,90,.6); } 100% { box-shadow: 0 0 0 .6rem rgba(30,158,90,0); } }
.central-acoes { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }
.seg { display: inline-flex; border: 1px solid var(--borda, #d9dee5); border-radius: 10px; overflow: hidden; }
.seg a { padding: .55rem .9rem; text-decoration: none; color: inherit; font-weight: 600; background: #fff; }
.central.tv .seg a { background: #16233a; }
.seg a + a { border-left: 1px solid var(--borda, #d9dee5); }
.seg a.ativo { background: var(--azul, #0c3a67); color: #fff; }
.central-acoes input.data { width: 10.5rem; flex: 0 0 auto; }

.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: .7rem; margin-bottom: .8rem; }
.kpi { background: #fff; border: 1px solid var(--borda, #d9dee5); border-radius: 12px; padding: .8rem 1rem; border-top: 5px solid; }
.kpi .n { font-size: 2.1rem; font-weight: 800; line-height: 1; }
.kpi .n small { font-size: 1rem; font-weight: 600; opacity: .6; }
.kpi .r { font-size: .85rem; margin-top: .3rem; opacity: .8; }
.k-azul { border-top-color: var(--azul-st); } .k-amarelo { border-top-color: var(--amarelo-st); }
.k-verde { border-top-color: var(--verde-st); } .k-roxo { border-top-color: var(--roxo); } .k-vermelho { border-top-color: var(--vermelho-st); }
.kpi.pulsa.k-amarelo { animation: pulsaAm 1.6s infinite; } .kpi.pulsa.k-vermelho { animation: pulsaVm 1.6s infinite; }
@keyframes pulsaAm { 50% { box-shadow: 0 0 0 4px rgba(224,161,0,.35); } }
@keyframes pulsaVm { 50% { box-shadow: 0 0 0 4px rgba(198,40,40,.3); } }

.legenda { display: flex; flex-wrap: wrap; gap: .4rem .9rem; font-size: .82rem; margin-bottom: 1rem; opacity: .85; }
.leg { display: inline-flex; align-items: center; gap: .35rem; }
.etapas-leg { flex-basis: 100%; display: block; }
.etapas-leg b { display: inline-grid; place-items: center; width: 1.1rem; height: 1.1rem; border-radius: 50%; border: 1.5px solid currentColor; font-size: .68rem; margin: 0 .1rem; }
.leg i { width: .85rem; height: .85rem; border-radius: 3px; display: inline-block; background: var(--c); }
.c-alerta { --c: var(--vermelho-st); }
.titulo-unidade { margin: 1.2rem 0 .6rem; }

/* cores por situação (variável --c usada por cartão, bolinhas e barras) */
.c-cinza { --c: var(--cinza); } .c-azul-claro { --c: var(--azul-claro); } .c-azul { --c: var(--azul-st); }
.c-amarelo { --c: var(--amarelo-st); } .c-ciano { --c: var(--ciano); } .c-verde { --c: var(--verde-st); }
.c-roxo { --c: var(--roxo); } .c-verde-escuro { --c: var(--verde-escuro); } .c-lilas { --c: #b9a3e3; }
.k-cinza { border-top-color: var(--cinza); } .k-ciano { border-top-color: var(--ciano); }
.avisos li.leve { color: #6b4b00; }
.chamados-sala, .na-farmacia { margin: 0 .9rem; display: flex; flex-wrap: wrap; gap: .3rem; }
.chip-ch { font-size: .78rem; font-weight: 600; padding: .2rem .55rem; border-radius: 999px; background: #fff4e5; border: 1px solid #f0c37a; }
.chip-ch.ch-direcionado { background: #eaf3ff; border-color: #a9c8f0; }
.na-farmacia { flex-direction: column; background: #f4effc; border-radius: 8px; padding: .35rem .55rem; font-size: .82rem; }
.central.tv .na-farmacia { background: #2a2346; } .central.tv .chip-ch { background: #4a3a1f; border-color: #8a6a2a; color: #ffe2b0; }

.grade-salas { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: .9rem; margin-bottom: 1.2rem; }
.sala { all: unset; box-sizing: border-box; cursor: pointer; display: flex; flex-direction: column; gap: .45rem;
  background: #fff; border: 1px solid var(--borda, #d9dee5); border-radius: 14px; overflow: hidden; padding: 0 0 .7rem;
  box-shadow: 0 1px 3px rgba(12,58,103,.06); transition: transform .12s, box-shadow .12s; }
.central.tv .sala { background: #16233a; border-color: #23344f; }
.sala:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(12,58,103,.12); }
.sala:focus-visible { outline: 3px solid var(--c); outline-offset: 2px; }
.sala.escolhida { outline: 3px solid var(--c); }
.sala-topo { display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .55rem .9rem;
  background: var(--c); color: #fff; }
.c-cinza .sala-topo, .c-azul-claro .sala-topo, .c-lilas .sala-topo { color: #10233a; }
.sala-num { font-size: 2rem; font-weight: 800; line-height: 1; display: flex; flex-direction: column; }
.sala-num small { font-size: .62rem; letter-spacing: .12em; font-weight: 700; opacity: .85; }
.sala-sit { font-weight: 700; text-align: right; font-size: .92rem; }
.sala.pulsa .sala-topo { animation: piscaTopo 1.4s ease-in-out infinite; }
@keyframes piscaTopo { 50% { filter: brightness(1.18); } }
.sala.alerta { border: 2px solid var(--vermelho-st); }
.paciente, .espec, .info, .passos, .avisos, .fila, .vazia { margin: 0 .9rem; }
.paciente { font-size: 1.02rem; }
.espec { font-size: .85rem; opacity: .75; }
.vazia { opacity: .6; font-size: .9rem; padding: .6rem 0; }
.passos { list-style: none; padding: 0; display: grid; grid-template-columns: repeat(6, 1fr); position: relative; margin-top: .3rem; }
.passos::before { content: ''; position: absolute; top: .72rem; left: 8%; right: 8%; height: 3px; background: #e3e7ed; }
.central.tv .passos::before { background: #2b3d59; }
.passos li { display: flex; flex-direction: column; align-items: center; gap: .15rem; position: relative; z-index: 1; }
.bola { width: 1.45rem; height: 1.45rem; border-radius: 50%; display: grid; place-items: center; font-size: .72rem; font-weight: 700;
  background: #fff; border: 2px solid #cfd6df; color: #8a94a3; }
.central.tv .bola { background: #16233a; border-color: #34496a; }
.passos li.feito .bola { background: var(--c); border-color: var(--c); color: #fff; }
.passos li.pulado .bola { border-style: dashed; color: #b5bdc8; }
.passos li.agora .bola { border-color: var(--c); color: var(--c); box-shadow: 0 0 0 4px color-mix(in srgb, var(--c) 25%, transparent); }
.hora { font-size: .68rem; opacity: .75; min-height: .9rem; }
.info { display: flex; flex-direction: column; gap: .15rem; font-size: .86rem; }
.avisos { list-style: none; padding: .45rem .6rem; border-radius: 8px; background: #fdecea; color: #8e1c1c; font-size: .82rem; font-weight: 600; }
.central.tv .avisos { background: #4a1f24; color: #ffd2d2; }
.fila { display: flex; align-items: center; gap: .3rem; font-size: .75rem; opacity: .8; margin-top: auto; padding-top: .3rem; }
.fila span { margin-left: .3rem; }
.pt { width: .7rem; height: .7rem; border-radius: 50%; background: var(--c); display: inline-block; }
.pt.atual { outline: 2px solid var(--c); outline-offset: 2px; }

/* linha do tempo */
.gantt-cartao h2 { margin-top: 0; }
.gantt { font-size: .8rem; }
.g-eixo, .g-linha { display: grid; grid-template-columns: 5.5rem 1fr; align-items: center; }
.g-linha { height: 1.9rem; border-top: 1px solid #eef1f5; cursor: pointer; }
.central.tv .g-linha { border-top-color: #23344f; }
.g-linha:hover { background: rgba(12,58,103,.04); }
.g-rot { font-weight: 700; white-space: nowrap; }
.g-trilha { position: relative; height: 100%; }
.g-eixo .g-trilha { height: 1.4rem; }
.g-h { position: absolute; transform: translateX(-50%); top: 0; opacity: .65; }
.g-grade { position: absolute; top: 0; bottom: 0; width: 1px; background: #eef1f5; }
.central.tv .g-grade { background: #23344f; }
.g-agora { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--vermelho-st); z-index: 3; }
.g-barra { position: absolute; top: .4rem; height: 1.1rem; border-radius: 5px; background: var(--c); opacity: .9; z-index: 1; }
.g-bip { position: absolute; top: .25rem; height: 1.4rem; width: 2px; background: #10233a; z-index: 2; opacity: .75; }
.central.tv .g-bip { background: #fff; }
.g-agendado { position: absolute; top: .55rem; width: .75rem; height: .75rem; transform: translateX(-50%) rotate(45deg);
  border: 2px solid var(--azul-claro); background: transparent; }

/* painel lateral */
.fundo { position: fixed; inset: 0; background: rgba(10,20,35,.35); z-index: 10000; }
.lateral { position: fixed; top: 0; right: 0; bottom: 0; width: min(440px, 100vw); background: #fff; color: #10233a; z-index: 10001;
  box-shadow: -8px 0 30px rgba(0,0,0,.2); display: flex; flex-direction: column; }
.lat-topo { background: var(--c); color: #fff; padding: 1rem 1.2rem; display: flex; justify-content: space-between; align-items: flex-start; }
.lat-topo h2 { margin: 0; color: inherit; font-size: 1.8rem; }
.fechar { all: unset; cursor: pointer; font-size: 1.3rem; padding: .2rem .5rem; }
.lat-corpo { overflow: auto; padding: 1rem 1.2rem; flex: 1; }
.lat-proc { border: 1px solid var(--borda, #d9dee5); border-radius: 10px; margin-bottom: .7rem; overflow: hidden; }
.lat-cab { all: unset; box-sizing: border-box; width: 100%; cursor: pointer; display: flex; gap: .6rem; align-items: center; padding: .6rem .8rem; }
.lat-proc.aberto .lat-cab { background: #f3f6fa; }
.lat-det { padding: .6rem .8rem .9rem; }
.etapas-lista > div { display: flex; align-items: center; gap: .5rem; padding: .25rem 0; font-size: .9rem; opacity: .55; }
.etapas-lista > div.feito, .etapas-lista > div.agora { opacity: 1; }
.etapas-lista > div.pulado { opacity: .45; font-style: italic; }
.etapas-lista .bola { width: 1.1rem; height: 1.1rem; font-size: .6rem; }
.etapas-lista .feito .bola { background: var(--verde-st); border-color: var(--verde-st); color: #fff; }
.lat-det h3 { margin: .8rem 0 .4rem; font-size: .95rem; }
.tempo { list-style: none; padding: 0; margin: 0 0 .8rem; border-left: 2px solid #dfe4ea; }
.tempo li { display: flex; gap: .6rem; padding: .3rem 0 .5rem .7rem; position: relative; font-size: .88rem; }
.tempo li::before { content: ''; position: absolute; left: -.4rem; top: .55rem; width: .65rem; height: .65rem; border-radius: 50%; background: var(--azul-st); }
.tempo li.ruim::before { background: var(--vermelho-st); }
.th { font-weight: 700; min-width: 2.8rem; }

@media (prefers-reduced-motion: reduce) { .sala.pulsa .sala-topo, .kpi.pulsa, .ao-vivo { animation: none; } }
@media (max-width: 640px) { .g-eixo, .g-linha { grid-template-columns: 3.6rem 1fr; } .sala-num { font-size: 1.6rem; } }
</style>
