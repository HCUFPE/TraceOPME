<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>{{ titulo }}</h1>
        <p><strong>{{ d.descricao }}</strong><template v-if="disp.paciente"> · {{ disp.paciente }}</template></p>
        <p class="pequeno">Dispensado pela farmácia ({{ disp.criado_por }}) em {{ f.dataHoraBr(disp.criado_em) }}
          <template v-if="disp.status === 'confirmada'"> · recebido na sala por <span class="etiqueta verde">{{ disp.recebido_por }}</span>
            em {{ f.dataHoraBr(disp.confirmada_em) }}</template></p>
      </div>
      <div class="acoes">
        <a class="botao" data-baixar :href="`/dispensacoes/${disp.id_dispensacao}/pdf`">Baixar PDF para a sala</a>
        <a v-if="d.finalizada" class="botao secundario" href="/farmacia/atendimentos"> Dispensar outro paciente</a>
        <a class="botao secundario" :href="d.voltar"> {{ d.finalizada ? 'Voltar à dispensação' : 'Voltar' }}</a>
      </div>
    </div>

    <template v-if="conferirSala">
      <!-- v18.3: primeiro abre a sala, depois dá ciência do material. -->
      <form v-if="d.pode_dar_ciencia && !d.sala_aberta" method="post" class="cartao abrir-primeiro"
            :action="`/sala-procedimento/atendimento/${disp.id_atendimento}/abrir-sala`">
        <input type="hidden" name="voltar" :value="`/sala-procedimento/atendimento/${disp.id_atendimento}`">
        <div>
          <h2 style="margin:0">1º passo: abrir a sala</h2>
          <p style="margin:.3rem 0 0">A sala ainda não foi aberta para este paciente. Abra a sala e, em seguida, dê ciência do material.</p>
        </div>
        <button class="botao" style="font-size:1.1rem;padding:.8rem 1.5rem">▶ Abrir sala</button>
      </form>
      <form method="post" :action="`/dispensacoes/${disp.id_dispensacao}/confirmar`" :class="['cartao', { bloqueado: d.pode_dar_ciencia && !d.sala_aberta }]" id="form-receb" @submit="aoEnviar">
        <h2>1. Confira o material ({{ disp.pendentes.length }})</h2>
        <div style="display:flex;gap:1.2rem;flex-wrap:wrap;margin:.3rem 0 .6rem">
          <label style="display:flex;gap:.4rem;align-items:center;font-weight:600">
            <input type="radio" name="modo" value="lista" v-model="modo" style="width:auto"> Conferir pela lista</label>
          <label style="display:flex;gap:.4rem;align-items:center;font-weight:600">
            <input type="radio" name="modo" value="bipando" v-model="modo" style="width:auto"> Conferir bipando o material</label>
        </div>
        <p v-if="modo === 'lista'" class="pequeno suave" id="ajuda-lista">Tudo vem marcado. <strong>Desmarque o que não chegou</strong> — fica como
          “não recebido” até a farmácia conferir onde está.</p>
        <div v-else id="bloco-bip">
          <p class="pequeno suave">Bipe cada material que chegou. Caixa de consignado: bipe o código da <strong>caixa</strong> — marca a caixa inteira.
            O que <strong>não</strong> for bipado fica como “não recebido” até a farmácia conferir onde está.</p>
          <label for="bip-receb">Bipe o código de barras</label>
          <input type="text" id="bip-receb" ref="campoBip" v-model="codigo" autocomplete="off" placeholder="aguardando leitura…"
                 style="font-size:1.4rem;padding:.7rem;text-align:center" @keydown.enter.prevent="bipar">
          <div style="display:flex;gap:1rem;align-items:center;margin:.5rem 0 .8rem;flex-wrap:wrap">
            <span class="etiqueta azul" style="font-size:1rem"><span id="bip-contagem">{{ Object.keys(bipados).length }}</span> de {{ disp.pendentes.length }} item(ns) bipado(s)</span>
            <span class="pequeno" id="bip-resultado" :style="{ color: resultado.ok ? 'var(--verde)' : 'var(--vermelho)' }">{{ resultado.texto }}</span>
          </div>
        </div>
        <div class="tabela-rolagem"><table>
          <thead><tr><th>Recebido?</th><th>Material</th><th>AGHU</th><th>Lote</th><th>Validade</th><th>Caixa</th></tr></thead>
          <tbody>
            <!-- Caixa de consignado: uma linha só — a sala confere a CAIXA, não cada item. -->
            <tr v-for="g in grupos" :key="'cx' + g.caixa" data-item="caixa" :style="linhaOk(g.valor) ? 'background:var(--verde-claro)' : ''">
              <td><input v-show="modo === 'lista'" type="checkbox" name="recebido" :value="g.valor" v-model="marcados[g.valor]"
                         :disabled="modo !== 'lista'" style="width:1.4rem;height:1.4rem">
                  <template v-if="modo === 'bipando'"><span v-if="completo(g.valor)" class="etiqueta verde marca-bip">✔ bipada</span>
                    <span v-else class="etiqueta cinza marca-falta">não bipada</span></template></td>
              <td colspan="4"><strong>Caixa {{ g.caixa }}</strong> — {{ g.itens.length }} item(ns)
                <details class="pequeno"><summary style="cursor:pointer">ver os itens</summary>
                  <div v-for="i in g.itens" :key="i.id_item">{{ i.descritivo_hospital || i.xProd }} · AGHU {{ i.codigo_aghu || '—' }} · lote {{ i.nLote || '—' }} · val. {{ f.dataBr(i.dVal) || '—' }}</div>
                </details></td>
              <td class="mono pequeno">{{ g.caixa }}</td>
            </tr>
            <tr v-for="i in soltos" :key="i.id_item" :data-item="i.id_item" :style="linhaOk(String(i.id_item)) ? 'background:var(--verde-claro)' : ''">
              <td><input v-show="modo === 'lista'" type="checkbox" name="recebido" :value="String(i.id_item)" v-model="marcados[String(i.id_item)]"
                         :disabled="modo !== 'lista'" style="width:1.4rem;height:1.4rem">
                  <template v-if="modo === 'bipando'"><span v-if="completo(String(i.id_item))" class="etiqueta verde marca-bip">✔ bipado</span>
                    <span v-else class="etiqueta cinza marca-falta">não bipado</span></template></td>
              <td>{{ i.descritivo_hospital || i.xProd }}</td>
              <td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td>
              <td class="mono">{{ i.nLote || '—' }}</td>
              <td class="pequeno">{{ f.dataBr(i.dVal) || '—' }}</td>
              <td class="mono pequeno">—</td>
            </tr>
          </tbody>
        </table></div>
        <div id="bipados-campos">
          <input v-for="id in Object.keys(bipados)" :key="id" type="hidden" name="bipado" :value="id">
        </div>
        <h2 style="margin-top:1.2rem">2. Dar ciência</h2>
        <template v-if="d.pode_dar_ciencia">
          <p class="pequeno">Fica registrado em nome de <strong>{{ d.nome_logado }}</strong> (usuário logado).</p>
          <button class="botao" :disabled="!d.sala_aberta">Dar ciência do recebimento</button>
          <span v-if="!d.sala_aberta" class="pequeno suave"> Abra a sala primeiro.</span>
        </template>
        <p v-else class="aviso alerta" style="margin:0">Quem dá ciência é a sala de procedimento. Entre com o usuário da sala
          para confirmar o recebimento.</p>
      </form>
      <template v-if="d.cancelar_sala">
        <p class="pequeno" style="margin:1rem 0 0"><strong>Ou:</strong> o procedimento não vai acontecer? Em vez de confirmar
          o recebimento, cancele — todo o material volta para a farmácia.</p>
        <CancelarProcedimento :acao="`/sala-procedimento/atendimento/${disp.id_atendimento}/cancelar`"
                              :dispensados="d.cancelar_sala" :motivos="d.motivos_cancelamento" />
      </template>
    </template>
    <template v-else>
      <div class="cartao">
        <h2>Material dispensado ({{ disp.itens.length }})</h2>
        <div class="tabela-rolagem"><table>
          <thead><tr><th>Material</th><th>AGHU</th><th>Lote</th><th>Validade</th><th>Caixa</th><th>Situação</th></tr></thead>
          <tbody>
            <tr v-for="i in disp.itens" :key="i.id_item">
              <td>{{ i.descritivo_hospital || i.xProd }}</td>
              <td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td>
              <td class="mono">{{ i.nLote || '—' }}</td>
              <td class="pequeno">{{ f.dataBr(i.dVal) || '—' }}</td>
              <td class="mono pequeno">{{ i.id_caixa || '—' }}</td>
              <td><span v-if="i.situacao === 'pendente'" class="etiqueta amarelo">aguardando a sala</span>
                  <span v-else-if="i.situacao === 'cancelado'" class="etiqueta cinza">voltou à farmácia (cancelado)</span>
                  <span v-else-if="i.situacao === 'nao_recebido'" class="etiqueta vermelho">sala não recebeu — farmácia conferindo</span>
                  <span v-else class="etiqueta verde">recebido</span></td>
            </tr>
          </tbody>
        </table></div>
      </div>
      <div v-if="d.finalizada" :class="['aviso', disp.status === 'confirmada' ? 'sucesso' : 'info']">
        <template v-if="disp.status === 'confirmada'">A sala já confirmou o recebimento.</template>
        <template v-else>O material saiu da farmácia. Agora a sala abre a sala, confere os materiais e confirma o
          recebimento com seu usuário, na tela da Sala de procedimento — sem bipar de novo.</template>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue';
import CancelarProcedimento from '../../components/opme/CancelarProcedimento.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, getJson } = useTela();

const disp = computed(() => props.d.disp);
const titulo = computed(() => {
  if (props.d.finalizada) return 'Dispensa finalizada';
  if (disp.value.status === 'confirmada') return 'Recebimento confirmado';
  if (disp.value.status === 'cancelada') return 'Procedimento cancelado — material devolvido à farmácia';
  return 'Confirmar recebimento na sala';
});
const conferirSala = computed(() => !props.d.finalizada && disp.value.status === 'pendente' && disp.value.pendentes?.length);

const grupos = computed(() => {
  const mapa: Record<string, any[]> = {};
  (disp.value.pendentes || []).filter((i: any) => i.id_caixa).forEach((i: any) => {
    (mapa[i.id_caixa] = mapa[i.id_caixa] || []).push(i);
  });
  return Object.keys(mapa).sort().map((caixa) => ({
    caixa, itens: mapa[caixa], valor: mapa[caixa].map((i: any) => i.id_item).join(','),
  }));
});
const soltos = computed(() => (disp.value.pendentes || []).filter((i: any) => !i.id_caixa));
const valores = computed(() => [...grupos.value.map((g) => g.valor), ...soltos.value.map((i: any) => String(i.id_item))]);

const modo = ref<'lista' | 'bipando'>('lista');
const marcados = reactive<Record<string, boolean>>({});
watch(valores, (vs) => vs.forEach((v) => { if (!(v in marcados)) marcados[v] = true; }), { immediate: true });
const bipados = reactive<Record<string, boolean>>({});
const codigo = ref('');
const resultado = reactive({ ok: true, texto: '' });
const campoBip = ref<HTMLInputElement | null>(null);

function completo(valor: string) { return valor.split(',').every((id) => !!bipados[id]); }
function linhaOk(valor: string) { return modo.value === 'bipando' && completo(valor); }

watch(modo, async (m) => { if (m === 'bipando') { await nextTick(); campoBip.value?.focus(); } });

function som(freq: number) {
  try {
    const c = new (window.AudioContext || (window as any).webkitAudioContext)();
    const o = c.createOscillator();
    o.frequency.value = freq; o.connect(c.destination); o.start(); o.stop(c.currentTime + 0.12);
  } catch { /* som é acessório */ }
}

async function bipar() {
  const c = codigo.value.trim();
  codigo.value = '';
  if (!c) return;
  try {
    const r: any = await getJson(`/dispensacoes/${disp.value.id_dispensacao}/identificar`, { codigo: c });
    const ids: string[] = r.ok ? (r.itens || []).map(String) : [];
    const livres = ids.filter((id) => !bipados[id]);
    const novos = r.caixa ? livres : livres.slice(0, 1);
    if (novos.length) {
      novos.forEach((id) => { bipados[id] = true; });
      resultado.ok = true;
      resultado.texto = `✔ ${c} — recebido${novos.length > 1 ? ` (${novos.length} itens da caixa).` : '.'}`;
      som(880);
    } else {
      resultado.ok = false;
      resultado.texto = r.ok ? `✖ ${c} — já bipado.` : `✖ ${r.mensagem}`;
      som(200);
    }
  } catch {
    resultado.ok = false;
    resultado.texto = 'Falha de conexão — bipe de novo.';
  } finally {
    campoBip.value?.focus();
  }
}

function aoEnviar(e: Event) {
  const b = modo.value === 'bipando';
  const recebidos = valores.value.filter((v) => (b ? completo(v) : marcados[v])).length;
  const faltam = valores.value.length - recebidos;
  if (recebidos === 0) {
    e.preventDefault();
    window.alert(`Nenhum item ${b ? 'bipado' : 'marcado'}. Marque o que chegou.`);
    return;
  }
  if (faltam > 0 && !window.confirm(`${faltam} item(ns) ${b ? 'não foram bipados' : 'foram desmarcados'}`
      + ' e voltarão ao estoque da farmácia como NÃO recebidos pela sala. Confirmar assim mesmo?')) e.preventDefault();
}
</script>

<style scoped>
.abrir-primeiro { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; border-left: 6px solid #1f6fc4; background: #f3f7fc; }
.bloqueado { opacity: .55; }
</style>
