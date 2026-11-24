<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Finalizar registro de uso e devoluções — prontuário {{ at.prontuario }}</h1>
        <p>{{ d.descricao }}<template v-if="at.paciente"> · {{ at.paciente }}</template></p>
      </div>
      <div class="acoes">
        <a class="botao secundario" :href="`/bipagem/registrar_uso?atendimento=${at.id_atendimento}`">Voltar a bipar</a>
      </div>
    </div>

    <div class="aviso">
      Confira o que foi usado no paciente. Se algum bip entrou por engano (duplicado, paciente errado,
      material que não foi usado), exclua aqui. Ao <strong>finalizar</strong>, os materiais selecionados abaixo
      serão registrados como <strong>pendentes de devolução à farmácia</strong>. Encaminhe-os fisicamente para
      conferência e confirmação do recebimento — a farmácia confere, dá ciência e conclui o procedimento.
    </div>

    <div v-if="d.entregas?.length" class="cartao alerta-entrega-cartao">
      <h2>Caixa a entregar ao paciente</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Material</th><th>AGHU</th><th>Lote</th><th>Ciência</th></tr></thead>
          <tbody>
            <tr v-for="e in d.entregas" :key="e.id_unidade">
              <td><strong>{{ e.descritivo_hospital || e.xProd }}</strong></td>
              <td class="mono">{{ e.codigo_aghu }}</td>
              <td class="mono">{{ e.nLote || '—' }}</td>
              <td>
                <span v-if="e.ciencia_por" class="etiqueta verde">ciente — {{ e.ciencia_por }}, {{ f.dataHoraBr(e.ciencia_em) }}</span>
                <form v-else method="post" style="margin:0"
                      :action="`/sala-procedimento/atendimento/${at.id_atendimento}/ciencia/${e.id_unidade}`">
                  <button class="botao perigo pequeno">Estou ciente: vou entregar a caixa ao paciente</button>
                </form>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>


    <form method="post" :action="`/sala-procedimento/atendimento/${at.id_atendimento}/finalizar-uso`"
          id="form-finalizar" :data-confirmar="perguntaFinalizar">
      <!-- v18.19: 1º as pendências de ciência (o que a farmácia mandou depois da abertura da sala),
           2º o que foi bipado, 3º o que volta para a farmácia. -->
      <div v-if="d.complemento?.length" id="pendencias-ciencia" class="cartao"
           style="border-left:5px solid var(--vermelho, #b3261e)">
        <h2>1. Pendência: {{ d.complemento.length }} material(is) recebido(s) sem ciência</h2>
        <p class="suave pequeno" style="margin:.2rem 0 .6rem">A farmácia dispensou estes itens
          <strong>depois que a sala já estava aberta</strong> e a ciência do recebimento ainda não foi dada.
          Confira item a item e dê a ciência para finalizar.</p>
        <div class="tabela-rolagem">
          <table>
            <thead><tr><th>Material</th><th>AGHU</th><th>Lote</th><th>Dispensado</th><th>Situação</th></tr></thead>
            <tbody>
              <tr v-for="(i, n) in d.complemento" :key="n">
                <td><strong>{{ i.descritivo_hospital || i.xProd }}</strong>
                  <template v-if="i.id_caixa"><br><span class="pequeno suave">caixa {{ i.id_caixa }}</span></template></td>
                <td class="mono">{{ i.codigo_aghu || '—' }}</td>
                <td class="mono">{{ i.nLote || '—' }}</td>
                <td class="pequeno suave">{{ i.bipado_por }}<br>{{ f.dataHoraBr(i.bipado_em) }}</td>
                <td class="pequeno">
                  <span v-if="i.status_unidade === 'utilizado'" class="etiqueta verde">já bipado como utilizado</span>
                  <span v-else class="etiqueta amarelo">na sala — volta se não for usado</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <label style="display:flex;gap:.5rem;align-items:flex-start;font-weight:600;margin-top:.7rem">
          <input type="checkbox" name="ciencia_complemento" value="1" required style="width:auto;margin-top:.2rem">
          Dou ciência do recebimento destes materiais na sala (fica registrado com o meu usuário).</label>
      </div>

      <div class="cartao">
        <h2>{{ d.complemento?.length ? '2. ' : '' }}{{ d.usados.length }} material(is) bipado(s) neste paciente</h2>
        <div v-if="d.usados.length" class="tabela-rolagem">
          <table>
            <thead><tr><th>Produto</th><th>AGHU</th><th>Lote</th><th>Validade</th><th>Bipado em</th><th>Excluir bip</th></tr></thead>
            <tbody>
              <tr v-for="m in d.usados" :key="m.id_unidade">
                <td>{{ m.descritivo_hospital || m.xProd }}<br><span class="suave pequeno">{{ m.fornecedor || '' }}</span></td>
                <td class="mono pequeno">{{ m.codigo_aghu || '—' }}</td>
                <td class="mono">{{ m.nLote || '—' }}</td>
                <td>{{ f.dataBr(m.dVal) || '—' }}</td>
                <td class="pequeno">{{ f.dataHoraBr(m.ultimo_movimento) }}</td>
                <td>
                  <form method="post" style="margin:0;display:flex;gap:.4rem;align-items:center"
                    :action="`/sala-procedimento/atendimento/${at.id_atendimento}/excluir/${m.id_unidade}`"
                    data-confirmar="Excluir este registro de uso? O material retornará à situação anterior permitida pelo sistema. A correção ficará registrada no histórico.">
                    <select name="motivo" required style="width:auto">
                      <option value="">motivo…</option>
                      <option>Bipado em duplicidade</option>
                      <option>Bipado no paciente errado</option>
                      <option>Material não foi utilizado</option>
                      <option>Material errado bipado</option>
                    </select>
                    <button class="botao secundario pequeno">Excluir</button>
                  </form>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="suave">Nenhum material bipado neste paciente.</p>
      </div>

      <div v-if="sobras.total" class="cartao" style="border-left:5px solid var(--amarelo, #b58100)">
        <h2>Não utilizados — pendentes de devolução à farmácia ({{ sobras.total }})</h2>
        <div style="display:flex;gap:1.2rem;flex-wrap:wrap;margin:.2rem 0 .6rem">
          <label style="display:flex;gap:.4rem;align-items:center;font-weight:600">
            <input type="radio" name="modo_sobras" value="lista" v-model="modo" style="width:auto"> Conferir pela lista</label>
          <label style="display:flex;gap:.4rem;align-items:center;font-weight:600">
            <input type="radio" name="modo_sobras" value="bipando" v-model="modo" style="width:auto"> Conferir bipando o material</label>
        </div>
        <p v-if="modo === 'lista'" class="suave pequeno" id="ajuda-sobras-lista">Tudo vem marcado. <strong>Desmarque o que não está devolvendo</strong> — o item
          continua com o paciente, como pendência da sala. O que está marcado fica pendente de devolução: leve fisicamente à farmácia, que confere e dá ciência.
          Algum destes foi usado? Volte a bipar o uso antes de finalizar.</p>
        <div v-else id="bloco-sobras-bip">
          <p class="suave pequeno">Bipe cada material que vai ser levado à farmácia. Só o que for bipado fica pendente de devolução
            (leve-o fisicamente à farmácia); o que <strong>não</strong> for bipado continua com o paciente, como pendência da sala.</p>
          <label for="bip-sobras">Bipe o código de barras (ou o código da caixa)</label>
          <input type="text" id="bip-sobras" ref="campoBip" v-model="codigo" autocomplete="off" placeholder="aguardando leitura…"
                 style="font-size:1.4rem;padding:.7rem;text-align:center" @keydown.enter.prevent="bipar">
          <div style="display:flex;gap:1rem;align-items:center;margin:.5rem 0 .8rem;flex-wrap:wrap">
            <span class="etiqueta azul" style="font-size:1rem"><span id="sobras-contagem">{{ Object.keys(bipados).length }}</span> de {{ chaves.length }} bipado(s)</span>
            <span class="pequeno" id="sobras-resultado" :style="{ color: resultado.ok ? 'var(--verde)' : 'var(--vermelho)' }">{{ resultado.texto }}</span>
          </div>
        </div>
        <div class="tabela-rolagem"><table>
          <thead><tr><th>Devolvido?</th><th>Material</th><th>AGHU</th><th>Lote</th><th>Validade</th></tr></thead>
          <tbody>
            <tr v-for="i in sobras.itens" :key="'u' + i.id_unidade" :data-chave="`u:${i.id_unidade}`"
                :style="modo === 'bipando' && bipados[`u:${i.id_unidade}`] ? 'background:var(--verde-claro)' : ''">
              <td><Marca :chave="`u:${i.id_unidade}`" /></td>
              <td>{{ i.descritivo_hospital || i.xProd }}</td><td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td>
              <td class="mono">{{ i.nLote || '—' }}</td><td class="pequeno">{{ f.dataBr(i.dVal) || '—' }}</td>
            </tr>
            <tr v-for="c in sobras.caixas" :key="'c' + c.id_caixa" :data-chave="`c:${String(c.id_caixa).toUpperCase()}`"
                :style="modo === 'bipando' && bipados[`c:${String(c.id_caixa).toUpperCase()}`] ? 'background:var(--verde-claro)' : ''">
              <td><Marca :chave="`c:${String(c.id_caixa).toUpperCase()}`" /></td>
              <td><strong>Caixa <span class="mono">{{ c.id_caixa }}</span></strong> {{ c.nome }} — {{ c.qtd }} item(ns)</td><td>—</td><td>—</td><td>—</td>
            </tr>
          </tbody>
        </table></div>
        <div id="sobras-campos">
          <input v-for="k in devolver" :key="k" type="hidden" name="devolver" :value="k">
        </div>
      </div>

      <div class="cartao" style="border-left:5px solid var(--verde)">
        <h2>{{ d.ja_finalizado ? 'Chegou material depois de finalizar' : 'Tudo certo?' }}</h2>
        <!-- v18.18: finalizar não trava mais a sala — ela segue bipando até a farmácia concluir. -->
        <p v-if="d.ja_finalizado" class="suave pequeno">Este prontuário já foi finalizado
          em {{ f.dataHoraBr(at.uso_finalizado_em) }}. Dê ciência do que chegou depois e finalize de novo:
          o que não for usado entra na lista da farmácia.</p>
        <p v-else class="suave pequeno">Depois de finalizar você continua podendo bipar o uso neste prontuário
           — inclusive material que chegar depois. A sala só fecha quando a farmácia concluir a conferência
           da devolução.</p>
        <p v-if="d.complemento?.length" class="aviso alerta pequeno" style="margin:.6rem 0">
          Confirme no topo da página a ciência dos {{ d.complemento.length }} material(is) recebidos depois —
          sem isso não dá para finalizar.</p>
        <button class="botao">{{ d.ja_finalizado ? 'Dar ciência e finalizar de novo' : 'Finalizar registro de uso e devoluções' }}</button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, nextTick, reactive, ref, watch } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, getJson } = useTela();
function som(freq: number) {
  try {
    const c = new (window.AudioContext || (window as any).webkitAudioContext)();
    const o = c.createOscillator();
    o.frequency.value = freq; o.connect(c.destination); o.start(); o.stop(c.currentTime + 0.12);
  } catch { /* som é acessório */ }
}

const at = computed(() => props.d.atendimento);
const sobras = computed(() => props.d.sobras || { total: 0, itens: [], caixas: [] });
const chaves = computed<string[]>(() => [
  ...(sobras.value.itens || []).map((i: any) => `u:${i.id_unidade}`),
  ...(sobras.value.caixas || []).map((c: any) => `c:${String(c.id_caixa).toUpperCase()}`),
]);

const modo = ref<'lista' | 'bipando'>('lista');
const marcados = reactive<Record<string, boolean>>({});
const bipados = reactive<Record<string, boolean>>({});
watch(chaves, (ks) => ks.forEach((k) => { if (!(k in marcados)) marcados[k] = true; }), { immediate: true });

const codigo = ref('');
const resultado = reactive({ ok: true, texto: '' });
const campoBip = ref<HTMLInputElement | null>(null);

const devolver = computed(() => (modo.value === 'bipando'
  ? Object.keys(bipados)
  : chaves.value.filter((k) => marcados[k])));

// v18.4.4: caixa conta pelas unidades que tem dentro (uma caixa com 20 itens = 20 materiais).
const qtdDaChave = (k: string): number => {
  if (!k.startsWith('c:')) return 1;
  const c = (sobras.value.caixas || []).find((x: any) => `c:${String(x.id_caixa).toUpperCase()}` === k);
  return Number(c?.qtd) || 1;
};
const perguntaFinalizar = computed(() => {
  const ficam = sobras.value.total ? chaves.value.filter((k) => !devolver.value.includes(k)) : [];
  const faltam = ficam.reduce((s, k) => s + qtdDaChave(k), 0);
  const devolve = devolver.value.reduce((s, k) => s + qtdDaChave(k), 0);
  if (faltam > 0) {
    const como = modo.value === 'bipando' ? 'não foram bipados' : 'foram desmarcados';
    return `${faltam} material(is) ${como} e vão continuar com o paciente (pendência da sala). `
      + (devolve ? `${devolve} material(is) ficam pendentes de devolução à farmácia. ` : '') + 'Finalizar assim mesmo?';
  }
  return (devolve ? `${devolve} material(is) serão registrados como pendentes de devolução à farmácia — encaminhe-os `
    + 'fisicamente para conferência. ' : '')
    + 'Finalizar o registro de uso deste prontuário? Depois disso a sala não bipa mais uso neste paciente.';
});

watch(modo, async (m) => { if (m === 'bipando') { await nextTick(); campoBip.value?.focus(); } });

async function bipar() {
  const c = codigo.value.trim();
  codigo.value = '';
  if (!c) return;
  try {
    const r: any = await getJson(`/sala-procedimento/atendimento/${at.value.id_atendimento}/sobras/identificar`, { codigo: c });
    const livre = r.ok ? (r.chaves || []).find((k: string) => !bipados[k]) : null;
    if (livre) {
      bipados[livre] = true;
      resultado.ok = true;
      resultado.texto = `✔ ${c} — marcado para devolver.`;
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

/** Marca da coluna "Devolvido?": checkbox na lista, etiqueta na bipagem. */
const Marca = defineComponent({
  props: { chave: { type: String, required: true } },
  setup(p) {
    return () => {
      if (modo.value === 'lista') {
        return h('input', {
          type: 'checkbox', class: 'marca-lista', value: p.chave, checked: marcados[p.chave],
          style: 'width:1.4rem;height:1.4rem',
          onChange: (e: Event) => { marcados[p.chave] = (e.target as HTMLInputElement).checked; },
        });
      }
      return bipados[p.chave]
        ? h('span', { class: 'etiqueta verde marca-bip' }, '✔ bipado')
        : h('span', { class: 'etiqueta cinza marca-falta' }, 'não bipado');
    };
  },
});
</script>
