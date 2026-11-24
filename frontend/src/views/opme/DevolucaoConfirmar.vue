<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>{{ dev.status === 'confirmada' ? 'Ciência da devolução registrada' : 'Não utilizados — conferir e dar ciência' }}</h1>
        <p><strong>{{ d.descricao }}</strong><template v-if="dev.paciente"> · {{ dev.paciente }}</template></p>
        <p class="pequeno">Devolvido por <span class="etiqueta azul">{{ dev.devolvido_por || '—' }}</span>
          · lista enviada em {{ f.dataHoraBr(dev.criado_em) }} (login {{ dev.criado_por }})
          <template v-if="dev.status === 'confirmada'"> · recebido por <span class="etiqueta verde">{{ dev.recebido_por }}</span>
            em {{ f.dataHoraBr(dev.confirmada_em) }}</template></p>
      </div>
      <div class="acoes"><a class="botao secundario" :href="d.voltar">Voltar</a></div>
    </div>

    <!-- v18.22: item "sem destino" que chegou fisicamente na farmácia. Fica FORA do
         formulário da conferência (form dentro de form não vale em HTML). -->
    <div v-if="dev.status === 'pendente' && semDestino.length" class="cartao" id="sem-destino">
      <h2 style="margin:0 0 .2rem">{{ semDestino.length }} material(is) sem destino</h2>
      <p class="pequeno suave" style="margin:0 0 .6rem">A sala não bipou o uso e não colocou na lista de não
        utilizados — por isso não há como marcar embaixo. <strong>Se o material está aqui na farmácia</strong>,
        inclua na lista e confirme junto com os demais. Se ele foi usado no paciente, quem bipa é a sala,
        na tela de bipagem do prontuário (dá para bipar mesmo com o uso já finalizado).</p>
      <div v-for="l in semDestino" :key="l.id_unidade" class="linha-sem-destino">
        <div>
          <strong>{{ l.material }}</strong> <span class="pequeno suave">AGHU {{ l.codigo_aghu || '—' }}</span><br>
          <span class="mono pequeno">lote {{ l.nLote || '—' }}<template v-if="l.validade"> · val. {{ l.validade }}</template></span>
        </div>
        <form method="post" :action="`/devolucoes/${dev.id_devolucao}/incluir-sem-destino`" style="margin:0"
              data-confirmar="Confirma que este material está aqui na farmácia? Ele entra na lista de não utilizados.">
          <input type="hidden" name="id_unidade" :value="l.id_unidade">
          <button class="botao pequeno">Recebi de volta — incluir na lista</button>
        </form>
      </div>
    </div>

    <form v-if="dev.status === 'pendente' && dev.pendentes?.length" method="post" :action="`/devolucoes/${dev.id_devolucao}/confirmar`"
          class="cartao" id="form-devolucao" @submit="aoEnviar">
      <h2>1. Confira o material ({{ dev.pendentes.length }})</h2>
      <div style="display:flex;gap:1.2rem;flex-wrap:wrap;margin:.3rem 0 .6rem">
        <label style="display:flex;gap:.4rem;align-items:center;font-weight:600">
          <input type="radio" name="modo" value="lista" v-model="modo" style="width:auto"> Conferir pela lista</label>
        <label style="display:flex;gap:.4rem;align-items:center;font-weight:600">
          <input type="radio" name="modo" value="bipando" v-model="modo" style="width:auto"> Conferir bipando o material</label>
      </div>
      <p v-if="modo === 'lista'" class="pequeno suave" id="ajuda-lista">Tudo vem marcado. <strong>Desmarque o que não voltou</strong> — o item continua com o
        paciente e a sala recebe um alerta para conferir (bipar o uso ou devolver). Depois, quem conclui é a farmácia.</p>
      <div v-else id="bloco-bipando">
        <p class="pequeno suave">Bipe cada material que chegou. Cada bip marca o item na lista. O que <strong>não</strong>
          for bipado fica como “não voltou” — o item continua com o paciente e a sala recebe o alerta.</p>
        <label for="bip-devolucao">Bipe o código de barras (ou o código da caixa)</label>
        <input type="text" id="bip-devolucao" ref="campoBip" v-model="codigo" autocomplete="off" placeholder="aguardando leitura…"
               style="font-size:1.4rem;padding:.7rem;text-align:center" @keydown.enter.prevent="bipar">
        <div style="display:flex;gap:1rem;align-items:center;margin:.5rem 0 .8rem;flex-wrap:wrap">
          <span class="etiqueta azul" style="font-size:1rem"><span id="bip-contagem">{{ Object.keys(bipados).length }}</span> de {{ dev.pendentes.length }} bipado(s)</span>
          <span class="pequeno" id="bip-resultado" :style="{ color: resultado.ok ? 'var(--verde)' : 'var(--vermelho)' }">{{ resultado.texto }}</span>
        </div>
      </div>
      <!-- v18.2: a lista inteira do que foi para o paciente — usado já vem marcado; confere-se o que voltou. -->
      <div class="balanco-resumo">
        <span class="bz bz-env"><b>{{ resumoBal.enviados }}</b> foram para o paciente</span>
        <span class="bz bz-uso"><b>{{ resumoBal.usado }}</b> usados</span>
        <span class="bz bz-volta"><b>{{ resumoBal.conferidos }}</b>/{{ resumoBal.devemVoltar }} voltaram (conferidos)</span>
        <span v-if="resumoBal.sem_destino" class="bz bz-falta"><b>{{ resumoBal.sem_destino }}</b> sem destino</span>
      </div>
      <p v-if="resumoBal.sem_destino" class="aviso alerta pequeno" style="margin:.4rem 0">
        {{ resumoBal.sem_destino }} item(ns) não foram bipados no paciente e não estão nesta lista de não utilizados.
        Se chegaram aqui, use <a href="#sem-destino">“Recebi de volta”</a> no quadro acima; se foram usados,
        a sala bipa o uso no prontuário.</p>
      <!-- v18.12.3: usado em cima, não utilizado embaixo — separados e com cores próprias,
           para a conferência do que voltou não se misturar com o que ficou no paciente. -->
      <div v-for="sec in secoes" :key="sec.chave" :class="['secao-bal', 'sec-' + sec.chave]">
        <div class="secao-cab">
          <strong>{{ sec.titulo }}</strong>
          <span class="etiqueta" :class="sec.cor">{{ sec.total }} unidade(s)</span>
          <span class="pequeno suave">{{ sec.ajuda }}</span>
        </div>
      <div v-for="g in sec.grupos" :key="g.chave" class="grupo-bal">
        <div class="grupo-cab">
          <strong>{{ g.material }}</strong>
          <span class="pequeno suave">AGHU {{ g.aghu || '—' }}</span>
          <span class="grupo-cont pequeno">{{ g.linhas.length }} enviado(s)
            <template v-if="g.usados"> · <b class="t-uso">{{ g.usados }} usado(s)</b></template>
            <template v-if="g.voltam"> · <b class="t-volta">{{ g.voltam }} para voltar</b></template>
            <template v-if="g.sem"> · <b class="t-falta">{{ g.sem }} sem destino</b></template></span>
        </div>
        <table class="tab-bal"><tbody>
          <tr v-for="l in g.linhas" :key="l.id_unidade + (l.id_item || '')" :class="'sit-' + estadoLinha(l)">
            <td class="col-marca">
              <template v-if="l.situacao === 'voltando'">
                <input v-if="modo === 'lista'" type="checkbox" name="recebido" :value="String(l.id_item)"
                       v-model="marcados[String(l.id_item)]" style="width:1.4rem;height:1.4rem" :aria-label="'Voltou: ' + l.material">
                <span v-else-if="bipados[String(l.id_item)]" class="etiqueta verde">✔ bipado</span>
                <span v-else class="etiqueta cinza">não bipado</span>
              </template>
              <span v-else-if="l.situacao === 'usado'" class="icone-sit icone-usado" title="Usado no paciente">USADO</span>
              <span v-else-if="l.situacao === 'na_caixa'" class="icone-sit" title="Volta dentro da caixa">▣</span>
              <span v-else-if="l.situacao === 'sem_destino'" class="icone-sit" title="Sem destino">!</span>
              <span v-else class="icone-sit">↩</span>
            </td>
            <td class="mono pequeno">lote {{ l.nLote || '—' }}<template v-if="l.numero_serie"> · série {{ l.numero_serie }}</template>
              <template v-if="l.validade"><br><span class="suave">val. {{ l.validade }}</span></template></td>
            <td>
              <template v-if="l.situacao === 'usado'"><span class="etiqueta etiqueta-usado">usado no paciente</span>
                <span class="pequeno"> {{ f.dataHoraBr(l.usado_em) }}<template v-if="l.usado_por"> · {{ l.usado_por }}</template></span>
                <span v-if="l.sem_dispensacao" class="etiqueta cinza pequeno">sem dispensação</span></template>
              <template v-else-if="l.situacao === 'voltando'">
                <span :class="['etiqueta', estadoLinha(l) === 'ok' ? 'verde' : estadoLinha(l) === 'falta' ? 'vermelho' : 'amarelo']">
                  {{ estadoLinha(l) === 'ok' ? 'voltou' : estadoLinha(l) === 'falta' ? 'não voltou' : 'conferir' }}</span>
                <span class="pequeno suave"> sala disse que não usou</span></template>
              <template v-else-if="l.situacao === 'na_caixa'">
                <span :class="['etiqueta', caixaMarcada(l.id_item) ? 'verde' : 'amarelo']">volta na caixa {{ l.caixa }}</span></template>
              <template v-else-if="l.situacao === 'sem_destino'"><span class="etiqueta vermelho">não usado e não está voltando</span></template>
              <template v-else><span class="etiqueta cinza">já voltou antes</span></template>
              <span v-if="l.caixa && l.situacao !== 'na_caixa'" class="pequeno suave"> · da caixa {{ l.caixa }}</span>
            </td>
          </tr>
        </tbody></table>
      </div>

      </div>

      <!-- Caixas desta lista: confere-se a caixa (a sala informou a contagem). -->
      <div v-for="cx in caixasPend" :key="'cx' + cx.id_item" class="grupo-bal grupo-caixa">
        <div class="grupo-cab">
          <input v-if="modo === 'lista'" type="checkbox" name="recebido" :value="String(cx.id_item)" v-model="marcados[String(cx.id_item)]"
                 style="width:1.4rem;height:1.4rem" :aria-label="'Caixa voltou: ' + cx.id_caixa">
          <span v-else :class="['etiqueta', bipados[String(cx.id_item)] ? 'verde' : 'cinza']">{{ bipados[String(cx.id_item)] ? '✔ bipada' : 'não bipada' }}</span>
          <strong>Caixa <span class="mono">{{ cx.id_caixa }}</span></strong> <span class="pequeno">{{ cx.nome_caixa || '' }}</span>
          <span class="grupo-cont pequeno">a sala contou <b>{{ cx.quantidade }}</b> · o sistema espera <b>{{ esperadoCaixa(cx.id_item) }}</b>
            <b v-if="Number(cx.quantidade) !== esperadoCaixa(cx.id_item)" class="t-falta"> — não bate</b></span>
        </div>
      </div>

      <!-- O que está na lista e não apareceu no balanço (por segurança, sempre conferível). -->
      <table v-if="avulsos.length" class="tab-bal"><tbody>
        <tr v-for="i in avulsos" :key="i.id_item">
          <td class="col-marca"><input v-if="modo === 'lista'" type="checkbox" name="recebido" :value="String(i.id_item)" v-model="marcados[String(i.id_item)]" style="width:1.4rem;height:1.4rem">
            <span v-else :class="['etiqueta', bipados[String(i.id_item)] ? 'verde' : 'cinza']">{{ bipados[String(i.id_item)] ? '✔ bipado' : 'não bipado' }}</span></td>
          <td>{{ i.descritivo_hospital || i.xProd }}</td><td class="mono pequeno">lote {{ i.nLote || '—' }}</td>
        </tr>
      </tbody></table>

      <div id="bipados-campos">
        <template v-if="modo === 'bipando'">
          <input v-for="id in Object.keys(bipados)" :key="id" type="hidden" name="bipado" :value="id">
        </template>
      </div>

      <template v-if="d.eh_farmacia">
        <h2 style="margin-top:1.2rem">2. Dar ciência</h2>
        <p class="pequeno">Fica registrado em nome de <strong>{{ auth.user?.nome || auth.user?.username }}</strong> (usuário logado).</p>
        <div class="campo" style="max-width:32rem">
          <label for="observacao">Observação <span class="opcional">(opcional)</span></label>
          <input type="text" id="observacao" name="observacao">
        </div>
        <button class="botao">Dar ciência da devolução</button>
      </template>
      <p v-else class="aviso">A ciência é dada pela farmácia, na tela da Farmácia → Não utilizados.</p>
    </form>
    <div v-else-if="dev.status === 'pendente'" class="cartao"><p class="vazio">Nada pendente nesta devolução.</p></div>

    <div v-if="resolvidos.length" class="cartao">
      <h2>Resultado</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Situação</th><th>Material</th><th>Lote</th><th>Devolvido por</th><th>Conferido em</th></tr></thead>
          <tbody>
            <tr v-for="i in resolvidos" :key="i.id_item">
              <td><span v-if="i.situacao === 'recebido'" class="etiqueta verde">recebido</span>
                  <span v-else-if="i.situacao === 'nao_recebido'" class="etiqueta vermelho">não recebido</span>
                  <span v-else class="etiqueta cinza">{{ i.situacao }}</span></td>
              <td><template v-if="i.tipo === 'caixa'">Caixa <span class="mono">{{ i.id_caixa }}</span> ({{ i.quantidade }} itens)</template><template v-else>{{ i.descritivo_hospital || i.xProd }}</template></td>
              <td class="mono">{{ i.nLote || '—' }}</td>
              <td class="pequeno">{{ i.devolvido_por || '—' }}</td>
              <td class="pequeno">{{ f.dataHoraBr(i.resolvido_em) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, auth, getJson } = useTela();

const dev = computed(() => props.d.dev);
const resolvidos = computed(() => (dev.value.itens || []).filter((i: any) => i.situacao !== 'pendente'));
const modo = ref<'lista' | 'bipando'>('lista');
const marcados = reactive<Record<string, boolean>>({});
const bipados = reactive<Record<string, boolean>>({});
watch(() => dev.value.pendentes, (ps) => (ps || []).forEach((i: any) => {
  if (!(String(i.id_item) in marcados)) marcados[String(i.id_item)] = true;
}), { immediate: true });
// ---- v18.2: balanço do paciente
const bal = computed(() => props.d.balanco || { linhas: [], resumo: {} });
const caixasPend = computed(() => (dev.value.pendentes || []).filter((i: any) => i.tipo === 'caixa'));
const avulsos = computed(() => {
  const vistos = new Set(bal.value.linhas.filter((l: any) => l.situacao === 'voltando').map((l: any) => String(l.id_item)));
  return (dev.value.pendentes || []).filter((i: any) => i.tipo !== 'caixa' && !vistos.has(String(i.id_item)));
});
function marcado(id: any): boolean {
  const k = String(id);
  return modo.value === 'lista' ? !!marcados[k] : !!bipados[k];
}
const caixaMarcada = (id: any) => marcado(id);
function estadoLinha(l: any): string {
  if (l.situacao === 'voltando') return marcado(l.id_item) ? 'ok' : (modo.value === 'lista' ? 'falta' : 'pendente');
  if (l.situacao === 'na_caixa') return marcado(l.id_item) ? 'ok' : 'pendente';
  return l.situacao;
}
const esperadoCaixa = (id: any) => bal.value.linhas.filter((l: any) => l.situacao === 'na_caixa' && String(l.id_item) === String(id)).length;
function agruparPorMaterial(linhas: any[]) {
  const m: Record<string, any> = {};
  for (const l of linhas) {
    const k = `${l.codigo_aghu}|${l.material}`;
    const g = (m[k] ||= { chave: k, material: l.material, aghu: l.codigo_aghu, linhas: [], usados: 0, voltam: 0, sem: 0 });
    g.linhas.push(l);
    if (l.situacao === 'usado') g.usados++;
    else if (l.situacao === 'voltando' || l.situacao === 'na_caixa') g.voltam++;
    else if (l.situacao === 'sem_destino') g.sem++;
  }
  return Object.values(m);
}
// v18.12.3: três blocos na ordem pedida — usados, pendências e, por último (junto do
// botão), o que a farmácia precisa conferir e marcar.
const SECOES = [
  { chave: 'usado', situacoes: ['usado', 'ja_voltou'], titulo: 'Usados no paciente', cor: 'azul',
    ajuda: '— ficaram com o paciente; nada a marcar aqui' },
  { chave: 'falta', situacoes: ['sem_destino'], titulo: 'Sem destino', cor: 'vermelho',
    ajuda: '— a sala não bipou o uso nem mandou de volta' },
  { chave: 'volta', situacoes: ['voltando', 'na_caixa'], titulo: 'Não utilizados — confira e marque o que voltou',
    cor: 'verde', ajuda: '— desmarque o que NÃO chegou à farmácia' },
];
const secoes = computed(() => SECOES.map((sec) => {
  const linhas = bal.value.linhas.filter((l: any) => sec.situacoes.includes(l.situacao));
  return { ...sec, total: linhas.length, grupos: agruparPorMaterial(linhas) };
}).filter((sec) => sec.total));
// v18.22: itens que a sala não bipou nem pôs na lista — a farmácia pode incluir
// aqui quando o material chega fisicamente. Caixa de consignado volta pela caixa.
const semDestino = computed(() => bal.value.linhas.filter(
  (l: any) => l.situacao === 'sem_destino' && !l.caixa));
const resumoBal = computed(() => {
  const ls = bal.value.linhas;
  const devem = ls.filter((l: any) => l.situacao === 'voltando' || l.situacao === 'na_caixa');
  return {
    enviados: ls.length, usado: ls.filter((l: any) => l.situacao === 'usado').length,
    sem_destino: ls.filter((l: any) => l.situacao === 'sem_destino').length,
    devemVoltar: devem.length + avulsos.value.length,
    conferidos: devem.filter((l: any) => marcado(l.id_item)).length + avulsos.value.filter((i: any) => marcado(i.id_item)).length,
  };
});
const codigo = ref('');
const resultado = reactive({ ok: true, texto: '' });
const campoBip = ref<HTMLInputElement | null>(null);

watch(modo, async (m) => {
  if (m === 'bipando') { await nextTick(); campoBip.value?.focus(); }
  else Object.keys(marcados).forEach((k) => { marcados[k] = true; });
});

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
    const r: any = await getJson(`/devolucoes/${dev.value.id_devolucao}/identificar`, { codigo: c });
    const livre = r.ok ? (r.itens || []).map(String).find((id: string) => !bipados[id]) : null;
    if (livre) {
      bipados[livre] = true;
      resultado.ok = true;
      resultado.texto = `✔ ${c} — marcado como recebido.`;
      som(880);
    } else {
      resultado.ok = false;
      resultado.texto = r.ok ? `✖ ${c} — já bipado (todos os desta lista já foram marcados).` : `✖ ${r.mensagem}`;
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
  if (modo.value !== 'bipando') return;
  const faltam = dev.value.pendentes.length - Object.keys(bipados).length;
  if (faltam > 0 && !window.confirm(`${faltam} item(ns) não foram bipados e ficarão como NÃO VOLTOU. Dar ciência assim mesmo?`)) {
    e.preventDefault();
  }
}
</script>

<style scoped>
.balanco-resumo { display: flex; flex-wrap: wrap; gap: .5rem; margin: .4rem 0 .8rem; }
.bz { padding: .45rem .8rem; border-radius: 999px; font-size: .9rem; border: 1px solid; }
.bz b { font-size: 1.1rem; }
.bz-env { border-color: #b8c4d3; background: #f2f5f9; }
.bz-uso { border-color: #b8c8ec; background: #dde6f7; color: #2f4f9e; }
.bz-volta { border-color: #e7c66b; background: #fff6dc; color: #6b4b00; }
.bz-falta { border-color: #efb0aa; background: #fdecea; color: #8e1c1c; }
.grupo-bal { border: 1px solid var(--borda, #d9dee5); border-radius: 10px; margin-bottom: .7rem; overflow: hidden; }
.grupo-cab { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem .8rem; padding: .55rem .8rem; background: #f4f6f9; }
.grupo-cont { margin-left: auto; }
.grupo-caixa { border-left: 5px solid #7a4fc4; }
.t-uso { color: #2f4f9e; }
.secao-bal { border-radius: 10px; padding: .5rem .7rem .2rem; margin: .8rem 0; border: 2px solid transparent; }
.secao-cab { display: flex; gap: .6rem; align-items: center; flex-wrap: wrap; margin-bottom: .3rem; }
.secao-cab strong { font-size: 1.05rem; }
.sec-usado { background: #eef3fb; border-color: #c6d4ee; }
.sec-usado .secao-cab strong { color: #2f4f9e; }
.sec-volta { background: #eaf7ef; border-color: #a9ddbf; }
.sec-volta .secao-cab strong { color: #14693c; }
.sec-falta { background: #fdecea; border-color: #f0b8b2; }
.sec-falta .secao-cab strong { color: var(--vermelho, #b3261e); }
.secao-bal .grupo-bal { background: #fff; } .t-volta { color: #8a6100; } .t-falta { color: #b3261e; }
.tab-bal { width: 100%; border-collapse: collapse; }
.tab-bal td { padding: .45rem .8rem; border-top: 1px solid #eef1f5; vertical-align: middle; }
.col-marca { width: 6.5rem; text-align: center; }
.icone-sit { display: inline-grid; place-items: center; width: 1.5rem; height: 1.5rem; border-radius: 50%; font-weight: 700; font-size: .85rem; }
/* v18.11.8: USADO em azul (etiqueta retangular) — não confunde com o quadrado verde do "voltou" */
tr.sit-usado { background: #eef3fb; }
.icone-usado { width: auto; height: auto; padding: .15rem .45rem; border-radius: 4px; background: #2f4f9e; color: #fff;
  font-size: .7rem; letter-spacing: .04em; }
.etiqueta-usado { background: #dde6f7; color: #2f4f9e; border: 1px solid #b8c8ec; }
tr.sit-ok { background: #eef9f2; }
tr.sit-falta, tr.sit-sem_destino { background: #fdf1f0; } tr.sit-sem_destino .icone-sit { background: #c62828; color: #fff; }
tr.sit-pendente { background: #fffbef; }
tr.sit-ja_voltou { opacity: .65; }
</style>
