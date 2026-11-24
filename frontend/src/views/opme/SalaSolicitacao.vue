<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Solicitação de OPME</h1>
        <p><strong>{{ d.descricao }}</strong><template v-if="at.paciente"> · {{ at.paciente }}</template></p>
        <p class="pequeno">Preencha a quantidade só do que precisa. A farmácia vê a solicitação na hora, na tela de
          dispensar, e cada material bipado dá o “check” na linha.</p>
      </div>
      <div class="acoes">
        <template v-if="d.pode_editar">
          <button class="botao secundario" form="form-solicitacao" name="seguir" value="gravar">Gravar solicitação</button>
          <button class="botao" form="form-solicitacao" name="seguir" value="concluir">Concluir solicitação</button>
        </template>
        <a v-else class="botao" :href="`/sala-procedimento/atendimento/${at.id_atendimento}`">Voltar</a>
      </div>
    </div>

    <template v-if="d.pode_editar">
      <form method="get" :action="`/sala-procedimento/atendimento/${at.id_atendimento}/solicitacao`" class="cartao"
            style="display:flex;gap:.6rem;align-items:flex-end;flex-wrap:wrap">
        <div class="campo" style="margin:0;flex:1 1 18rem"><label>Formulário</label>
          <select name="formulario" @change="trocarFormulario">
            <option v-for="(fo, chave) in d.formularios" :key="chave" :value="chave" :selected="chave === d.formulario">
              {{ fo.titulo }}{{ chave === d.sugerido ? ' (sugerido)' : '' }}{{ d.usados.includes(chave) ? ' · já pedido' : '' }}</option>
          </select></div>
        <button class="botao secundario">Abrir</button>
      </form>

      <form method="post" class="cartao" id="form-solicitacao" ref="formSol"
            :action="`/sala-procedimento/atendimento/${at.id_atendimento}/solicitacao`">
        <input type="hidden" name="formulario" :value="d.formulario">
        <h2>{{ d.formularios[d.formulario]?.titulo }}</h2>
        <div style="display:flex;gap:.8rem;align-items:flex-end;flex-wrap:wrap;margin-bottom:.6rem;position:sticky;top:0;background:var(--branco, #fff);padding:.4rem 0;z-index:2">
          <div class="campo" style="margin:0;flex:1 1 20rem">
            <label for="busca-item">Buscar material pela descrição ou código AGHU (neste formulário, nos outros e no cadastro)</label>
            <input type="search" id="busca-item" ref="campoBusca" v-model="busca" autocomplete="off"
                   style="width:100%;font-size:1.05rem;padding:.6rem .7rem" placeholder="ex.: introdutor 6  ·  23265  ·  fio guia"
                   @keydown.enter.prevent @input="agendarOutros">
          </div>
          <label class="pequeno" style="display:flex;align-items:center;gap:.35rem;font-weight:400;margin-bottom:.6rem">
            <input type="checkbox" id="so-preenchidos" v-model="soPreenchidos" style="width:auto"> só os que já têm quantidade</label>
        </div>
        <p v-if="termos.length" class="pequeno suave" id="busca-resultado">
          {{ visiveis ? `${visiveis} item(ns) encontrado(s) neste formulário.` : 'Nada encontrado neste formulário. Veja abaixo se está em outro formulário ou no cadastro de materiais.' }}
        </p>
        <div v-if="outros.length" id="busca-outros" class="aviso info" style="margin:.2rem 0 .8rem">
          <strong>Também encontrado em outros formulários e no cadastro de materiais</strong>
          <span class="pequeno"> — informe a quantidade e clique em “incluir”.</span>
          <table style="margin-top:.4rem"><tbody>
            <tr v-for="(it, n) in outros" :key="n">
              <td class="mono pequeno">{{ it.codigos || '—' }}</td>
              <td class="pequeno">{{ it.descricao }}<br><span class="suave">{{ it.origem }}{{ it.em_estoque ? ` · ${it.em_estoque} em estoque` : '' }}</span>
                <template v-if="it.pede_especificacao"><br><input type="text" v-model="it._espec" placeholder="tipo / tamanho" style="max-width:16rem;margin-top:.2rem"></template>
              </td>
              <td style="width:6rem"><input type="number" v-model="it._qtd" min="1" max="999" style="width:5rem"></td>
              <td style="white-space:nowrap"><button type="button" class="botao secundario pequeno" @click="incluir(it)">incluir</button>
                <span class="pequeno" :style="{ color: it._ok ? 'var(--verde)' : 'var(--vermelho)' }"> {{ it._msg }}</span></td>
            </tr>
          </tbody></table>
        </div>
        <table id="tabela-formulario">
          <thead><tr><th>Cód. AGHU</th><th>Descrição</th><th style="width:7rem">Qtd. solicitada</th></tr></thead>
          <tbody>
            <tr v-for="l in d.linhas" :key="l.linha" v-show="mostrar(l)" :data-busca="`${l.codigos} ${l.descricao}`">
              <td class="mono pequeno">{{ l.codigos ? l.codigos.replace(' ', ' / ') : '—' }}</td>
              <td class="pequeno">{{ l.descricao }}
                <input v-if="l.pede_especificacao" type="text" :name="`espec_${l.linha}`" :defaultValue="l.especificacao"
                       placeholder="tipo / tamanho" style="margin-top:.25rem;max-width:18rem"></td>
              <td><input type="number" :name="`qtd_${l.linha}`" min="0" max="999" inputmode="numeric"
                         :defaultValue="l.quantidade || ''" style="width:6rem"
                         @input="qtds[l.linha] = Number(($event.target as HTMLInputElement).value) || 0"></td>
            </tr>
          </tbody>
        </table>
        <div class="campo" style="margin-top:1rem"><label>Observação para a farmácia <span class="opcional">(opcional)</span></label>
          <input type="text" name="observacao" :defaultValue="d.observacao" placeholder="Ex.: urgente, paciente já na sala"></div>
        <div class="linha-botoes">
          <button class="botao secundario" name="seguir" value="gravar">Gravar solicitação</button>
          <button class="botao" name="seguir" value="concluir">Concluir solicitação</button>
        </div>
      </form>

      <form method="post" class="cartao" :action="`/sala-procedimento/atendimento/${at.id_atendimento}/solicitacao/avulso`">
        <h2>Material fora do formulário</h2>
        <div class="grade grade-3">
          <div class="campo"><label>Código AGHU</label><input type="text" name="codigo_aghu" inputmode="numeric"></div>
          <div class="campo"><label>Descrição <span class="opcional">(preenchida pelo AGHU se em branco)</span></label><input type="text" name="descricao"></div>
          <div class="campo"><label class="obrigatorio">Quantidade</label><input type="number" name="quantidade" min="1" max="999" defaultValue="1"></div>
        </div>
        <button class="botao secundario">Incluir na solicitação</button>
      </form>
    </template>
    <div v-else class="aviso info">A solicitação só pode ser alterada com o atendimento aberto e antes de finalizar os utilizados.</div>

    <div class="cartao" id="cartao-solicitado">
      <SolicitadoSala :sol="sol" :atendimento="at" :pode-editar="d.pode_editar" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import SolicitadoSala from '../../components/opme/SolicitadoSala.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { getJson, postJson, acao } = useTela();
const router = useRouter();

const at = computed(() => props.d.atendimento);
const sol = ref<any>(props.d.sol);
const busca = ref('');
const soPreenchidos = ref(false);
const qtds = reactive<Record<string, number>>({});
(props.d.linhas || []).forEach((l: any) => { qtds[l.linha] = Number(l.quantidade) || 0; });
const outros = ref<any[]>([]);
const formSol = ref<HTMLFormElement | null>(null);
const campoBusca = ref<HTMLInputElement | null>(null);

function norm(t: unknown) {
  return String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase()
    .replace(/[.,;:()/\-]+/g, ' ').replace(/\s+/g, ' ').trim();
}
const termos = computed(() => norm(busca.value).split(' ').filter(Boolean));
function mostrar(l: any) {
  const alvo = norm(`${l.codigos} ${l.descricao}`);
  return termos.value.every((t) => alvo.includes(t)) && (!soPreenchidos.value || qtds[l.linha] > 0);
}
const visiveis = computed(() => (props.d.linhas || []).filter(mostrar).length);

let timer: ReturnType<typeof setTimeout> | undefined;
let ultima = '';
function agendarOutros() {
  clearTimeout(timer);
  timer = setTimeout(buscarOutros, 300);
}
async function buscarOutros() {
  const q = busca.value.trim();
  if (q.length < 3) { outros.value = []; ultima = ''; return; }
  if (q === ultima) return;
  ultima = q;
  try {
    const r: any = await getJson('/sala-procedimento/solicitacao/buscar', { formulario: props.d.formulario, q });
    if (busca.value.trim() !== q) return;
    outros.value = (r.itens || []).map((it: any) => ({ ...it, _qtd: 1, _espec: '', _msg: '', _ok: false }));
  } catch { /* busca é auxiliar */ }
}

async function incluir(it: any) {
  try {
    const r: any = await postJson(`/sala-procedimento/atendimento/${at.value.id_atendimento}/solicitacao/incluir`, {
      codigo: it.codigos, descricao: it.descricao, quantidade: it._qtd, especificacao: it._espec,
    });
    it._ok = r.ok;
    it._msg = `${r.ok ? '✔' : '✖'} ${r.mensagem}`;
    if (r.ok) {
      const env: any = await getJson(`/sala-procedimento/atendimento/${at.value.id_atendimento}/solicitacao/painel`);
      if (env?.dados?.sol) sol.value = env.dados.sol;
    }
  } catch {
    it._ok = false;
    it._msg = '✖ Falha de conexão.';
  }
}

/** Trocar de formulário com quantidade digitada e não gravada: grava antes. */
function trocarFormulario(e: Event) {
  const valor = (e.target as HTMLSelectElement).value;
  const form = formSol.value;
  const mudou = !!form && Array.from(form.querySelectorAll('input')).some(
    (i) => (i.type === 'number' || i.type === 'text') && i.value !== i.defaultValue);
  if (mudou && form) {
    const fd = new FormData(form);
    fd.set('seguir', `formulario:${valor}`);
    acao(form.getAttribute('action') || '', fd);
  } else {
    router.push({ path: `/sala-procedimento/atendimento/${at.value.id_atendimento}/solicitacao`, query: { formulario: valor } });
  }
}

onMounted(() => campoBusca.value?.focus());
</script>
