<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Caixa {{ t.id_caixa }} — {{ t.local }}</h1>
        <p><strong>{{ t.nome_caixa }}</strong><template v-if="t.fornecedor"> · {{ t.fornecedor }}</template> · dia {{ f.dataBr(t.data) }} ·
           <span :class="['etiqueta', t.status === 'divergente' ? 'vermelho' : (t.status === 'devolvida' ? 'amarelo' : 'verde')]">{{ t.status_rotulo }}</span></p>
        <p class="pequeno suave">Enviada por {{ t.enviada_por }} em {{ f.dataHoraBr(t.enviada_em) }}
          <template v-if="t.recebida_nome"> · ciência da sala: {{ t.recebida_nome }} em {{ f.dataHoraBr(t.recebida_em) }}</template>
          <template v-if="t.devolvida_nome"> · devolvida por {{ t.devolvida_nome }} em {{ f.dataHoraBr(t.devolvida_em) }}</template>
          <template v-if="t.conferida_nome"> · conferida por {{ t.conferida_nome }} em {{ f.dataHoraBr(t.conferida_em) }}</template></p>
      </div>
      <div class="acoes">
        <a class="botao secundario" :href="`/farmacia/caixas-consignado/${t.id_caixa}`">Abrir a caixa</a>
        <a class="botao secundario" href="/farmacia/caixas-sala">Voltar</a>
      </div>
    </div>

    <div class="grade grade-4" style="margin-bottom:1.25rem">
      <div class="cartao"><div class="rotulo">enviados</div><div class="numero">{{ t.qtd_enviada }}</div></div>
      <div class="cartao"><div class="rotulo">usados nos pacientes</div><div class="numero">{{ t.usados }}</div></div>
      <div class="cartao"><div class="rotulo">{{ emCurso ? 'devem voltar' : 'voltaram' }}</div>
        <div class="numero">{{ emCurso ? t.restam : (t.qtd_voltou || 0) }}</div></div>
      <div class="cartao"><div class="rotulo">faltaram</div><div class="numero">{{ t.qtd_faltou || 0 }}</div></div>
    </div>

    <!-- v18.2: uma lista só — o que a caixa levou, o que foi usado (já marcado) e o que voltou (conferir). -->
    <form v-if="t.status === 'devolvida'" method="post" :action="`/farmacia/caixas-sala/${t.id_turno}/conferir`" class="cartao" id="form-conf"
          style="border-left:5px solid var(--verde)" @submit="confirmarFaltas">
      <h2>Conferir o retorno da caixa</h2>
      <input type="hidden" name="modo" :value="todosVoltaram ? 'confere' : 'itens'">
      <input v-for="id in presentes" :key="id" type="hidden" name="presente" :value="id">
      <div class="balanco-resumo">
        <span class="bz bz-env"><b>{{ d.itens.length }}</b> foram na caixa</span>
        <span class="bz bz-uso"><b>{{ usados.length }}</b> usados nos pacientes</span>
        <span class="bz bz-volta"><b>{{ presentes.length }}</b>/{{ devem.length }} conferidos de volta</span>
        <span v-if="faltando.length" class="bz bz-falta"><b>{{ faltando.length }}</b> não voltaram</span>
      </div>
      <div style="display:flex;gap:1.2rem;flex-wrap:wrap;align-items:center;margin:.3rem 0 .8rem">
        <label style="display:flex;gap:.4rem;align-items:center;font-weight:600">
          <input type="radio" value="lista" v-model="modo" style="width:auto"> Conferir pela lista</label>
        <label style="display:flex;gap:.4rem;align-items:center;font-weight:600">
          <input type="radio" value="bipando" v-model="modo" style="width:auto"> Conferir bipando o material</label>
        <button v-if="modo === 'lista'" type="button" class="botao secundario pequeno" @click="marcarTodos(true)">marcar todos como voltou</button>
        <button v-if="modo === 'lista'" type="button" class="botao secundario pequeno" @click="marcarTodos(false)">desmarcar todos</button>
      </div>
      <div v-if="modo === 'bipando'" style="margin-bottom:.8rem">
        <input type="text" ref="campoBip" v-model="codigo" autocomplete="off" placeholder="bipe cada item que voltou na caixa…"
               style="font-size:1.3rem;padding:.6rem;text-align:center" @keydown.enter.prevent="bipar">
        <div class="pequeno" :style="{ color: resultado.ok ? 'var(--verde)' : 'var(--vermelho)', marginTop: '.3rem' }">{{ resultado.texto }}</div>
      </div>
      <p class="pequeno suave" style="margin:0 0 .6rem">O que foi bipado nos pacientes já vem marcado como <strong>usado</strong>.
        Confira só o que deveria ter voltado. O que não voltar deixa a caixa <strong>bloqueada</strong> e a sala é avisada.</p>

      <div v-for="g in grupos" :key="g.chave" class="grupo-bal">
        <div class="grupo-cab"><strong>{{ g.material }}</strong><span class="pequeno suave">AGHU {{ g.aghu || '—' }}</span>
          <span class="grupo-cont pequeno">{{ g.linhas.length }} na caixa
            <template v-if="g.usados"> · <b class="t-uso">{{ g.usados }} usado(s)</b></template>
            <template v-if="g.devem"> · <b class="t-volta">{{ g.conferidos }}/{{ g.devem }} voltaram</b></template></span></div>
        <table class="tab-bal"><tbody>
          <tr v-for="i in g.linhas" :key="i.id_unidade" :class="'sit-' + estado(i)">
            <td class="col-marca">
              <span v-if="i.situacao === 'usado'" class="icone-sit">✔</span>
              <input v-else-if="modo === 'lista'" type="checkbox" :value="i.id_unidade" v-model="presentes" style="width:1.4rem;height:1.4rem"
                     :aria-label="'Voltou: ' + i.produto">
              <span v-else-if="presentes.includes(i.id_unidade)" class="etiqueta verde">✔ bipado</span>
              <span v-else class="etiqueta cinza">não bipado</span>
            </td>
            <td class="mono pequeno">lote {{ i.nLote || '—' }}<template v-if="i.numero_serie"> · série {{ i.numero_serie }}</template>
              <br><span class="suave">val. {{ f.dataBr(i.dVal) || '—' }}</span></td>
            <td>
              <template v-if="i.situacao === 'usado'"><span class="etiqueta verde">usado</span>
                <span class="pequeno"> prontuário {{ i.prontuario || '—' }}<template v-if="i.paciente"> · {{ i.paciente }}</template>
                  <template v-if="i.usado_em"> · {{ f.dataHoraBr(i.usado_em) }}</template><template v-if="i.usado_por"> · {{ i.usado_por }}</template></span></template>
              <span v-else-if="estado(i) === 'ok'" class="etiqueta verde">voltou</span>
              <span v-else-if="estado(i) === 'falta'" class="etiqueta vermelho">não voltou</span>
              <span v-else class="etiqueta amarelo">conferir</span>
            </td>
          </tr>
        </tbody></table>
      </div>
      <button class="botao" style="margin-top:.4rem">Dar ciência do retorno da caixa</button>
      <p class="pequeno suave" style="margin:.4rem 0 0">Fica registrado no login de quem está logado.</p>
    </form>
    <div v-else-if="['conferida', 'divergente'].includes(t.status) && t.usados" :class="['aviso', t.status === 'divergente' ? 'erro' : 'sucesso']">
      <template v-if="t.status === 'divergente'"><strong>Caixa bloqueada:</strong> {{ t.faltaram }} item(ns) não voltaram e a sala foi avisada.
        Depois de resolver, confira e libere em <a :href="`/farmacia/caixas-consignado/${t.id_caixa}`">Abrir a caixa</a>.</template>
      <template v-else><strong>Reabastecer:</strong> {{ t.usados }} item(ns) foram usados. Bipe a reposição em
        <a :href="`/farmacia/caixas-consignado/${t.id_caixa}`">Abrir a caixa</a>.</template>
    </div>

    <div v-if="t.status !== 'devolvida'" class="cartao">
      <h2>Itens da caixa neste dia</h2>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Material</th><th>AGHU</th><th>Lote</th><th>Validade</th><th>Série</th><th>Situação</th></tr></thead>
        <tbody>
          <tr v-for="(i, n) in d.itens" :key="n"><td>{{ i.produto }}</td><td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td><td class="mono">{{ i.nLote || '—' }}</td>
              <td>{{ f.dataBr(i.dVal) || '—' }}</td><td class="mono pequeno">{{ i.numero_serie || '—' }}</td>
              <td>
                <template v-if="i.situacao === 'usado'"><span class="etiqueta verde">usado</span> <span class="pequeno">prontuário {{ i.prontuario || '—' }} · {{ i.paciente || '' }}<template v-if="i.usado_em"> · {{ f.dataHoraBr(i.usado_em) }}</template></span></template>
                <span v-else-if="i.situacao === 'voltou'" class="etiqueta cinza">voltou na caixa</span>
                <span v-else-if="i.situacao === 'faltou'" class="etiqueta vermelho">não voltou</span>
                <span v-else class="etiqueta azul">na caixa</span>
              </td></tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, getJson } = useTela();
const t = computed(() => props.d.t);
const emCurso = computed(() => ['na_sala', 'devolvida', 'enviada'].includes(t.value.status));
const devem = computed(() => (props.d.itens || []).filter((i: any) => i.situacao === 'na_caixa'));
const usados = computed(() => (props.d.itens || []).filter((i: any) => i.situacao === 'usado'));
const modo = ref<'lista' | 'bipando'>('lista');
const presentes = ref<string[]>(devem.value.map((i: any) => i.id_unidade));
const faltando = computed(() => (modo.value === 'lista' ? devem.value.filter((i: any) => !presentes.value.includes(i.id_unidade)) : []));
const todosVoltaram = computed(() => presentes.value.length === devem.value.length);
const codigo = ref('');
const resultado = ref({ ok: true, texto: '' });
const campoBip = ref<HTMLInputElement | null>(null);

watch(modo, async (m) => {
  if (m === 'bipando') { presentes.value = []; await nextTick(); campoBip.value?.focus(); }
  else presentes.value = devem.value.map((i: any) => i.id_unidade);
});
function marcarTodos(sim: boolean) { presentes.value = sim ? devem.value.map((i: any) => i.id_unidade) : []; }
function estado(i: any): string {
  if (i.situacao === 'usado') return 'usado';
  if (presentes.value.includes(i.id_unidade)) return 'ok';
  return modo.value === 'lista' ? 'falta' : 'pendente';
}
const grupos = computed(() => {
  const m: Record<string, any> = {};
  for (const i of props.d.itens || []) {
    const k = `${i.codigo_aghu}|${i.produto}`;
    const g = (m[k] ||= { chave: k, material: i.produto, aghu: i.codigo_aghu, linhas: [], usados: 0, devem: 0, conferidos: 0 });
    g.linhas.push(i);
    if (i.situacao === 'usado') g.usados++;
    if (i.situacao === 'na_caixa') { g.devem++; if (presentes.value.includes(i.id_unidade)) g.conferidos++; }
  }
  return Object.values(m);
});

async function bipar() {
  const c = codigo.value.trim();
  codigo.value = '';
  if (!c) return;
  try {
    const r: any = await getJson(`/farmacia/caixas-sala/${t.value.id_turno}/identificar`, { codigo: c });
    const livre = r.ok ? (r.itens || []).find((id: string) => !presentes.value.includes(id)) : null;
    if (livre) { presentes.value.push(livre); resultado.value = { ok: true, texto: `✔ ${c} — voltou.` }; }
    else resultado.value = { ok: false, texto: r.ok ? `✖ ${c} — já bipado.` : `✖ ${r.mensagem}` };
  } catch { resultado.value = { ok: false, texto: 'Falha de conexão — bipe de novo.' }; }
  campoBip.value?.focus();
}

function confirmarFaltas(evento: Event) {
  const faltam = devem.value.length - presentes.value.length;
  if (faltam && !confirm(`${faltam} item(ns) não voltaram: a caixa fica BLOQUEADA com pendência e a sala é avisada. Confirmar?`)) evento.preventDefault();
}
void emCurso;
</script>

<style scoped>
.balanco-resumo { display: flex; flex-wrap: wrap; gap: .5rem; margin: .4rem 0 .8rem; }
.bz { padding: .45rem .8rem; border-radius: 999px; font-size: .9rem; border: 1px solid; }
.bz b { font-size: 1.1rem; }
.bz-env { border-color: #b8c4d3; background: #f2f5f9; }
.bz-uso { border-color: #9fd3b4; background: #e6f5ec; color: #145c35; }
.bz-volta { border-color: #e7c66b; background: #fff6dc; color: #6b4b00; }
.bz-falta { border-color: #efb0aa; background: #fdecea; color: #8e1c1c; }
.grupo-bal { border: 1px solid var(--borda, #d9dee5); border-radius: 10px; margin-bottom: .7rem; overflow: hidden; }
.grupo-cab { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem .8rem; padding: .55rem .8rem; background: #f4f6f9; }
.grupo-cont { margin-left: auto; }
.t-uso { color: #1e7a45; } .t-volta { color: #8a6100; }
.tab-bal { width: 100%; border-collapse: collapse; }
.tab-bal td { padding: .45rem .8rem; border-top: 1px solid #eef1f5; vertical-align: middle; }
.col-marca { width: 6.5rem; text-align: center; }
.icone-sit { display: inline-grid; place-items: center; width: 1.5rem; height: 1.5rem; border-radius: 50%; font-weight: 700; font-size: .85rem; }
tr.sit-usado { background: #f3faf6; } tr.sit-usado .icone-sit { background: #1e9e5a; color: #fff; }
tr.sit-ok { background: #eef9f2; } tr.sit-falta { background: #fdf1f0; } tr.sit-pendente { background: #fffbef; }
</style>
