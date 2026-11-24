<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Material não cadastrado no sistema</h1>
        <p><strong>{{ d.descricao }}</strong><template v-if="at.paciente"> · {{ at.paciente }}</template></p>
      </div>
      <div class="acoes">
        <a class="botao secundario" :href="`/bipagem/registrar_uso?atendimento=${at.id_atendimento}`">Voltar a bipar</a>
      </div>
    </div>

    <div class="aviso erro" style="border:3px solid var(--vermelho, #b3261e)">
      <strong>Cole a etiqueta do material no formulário de rastreabilidade.</strong>
      Informe lote e validade da etiqueta (pesquisar o material pelo nome é opcional). O almoxarifado é avisado
      para regularizar o cadastro.
    </div>

    <form method="post" :action="`/sala-procedimento/atendimento/${at.id_atendimento}/nao-cadastrado`" class="cartao" autocomplete="off">
      <h2>Material</h2>
        <div v-if="!escolhido" class="campo" style="position:relative">
          <label>Pesquise o material pelo nome ou código AGHU <span class="opcional">(opcional)</span></label>
          <input type="text" v-model="busca" ref="campoBusca" placeholder="ex.: placa titânio, parafuso cortical" @input="digitando"
                 @keydown.enter.prevent>
          <p v-if="buscando" class="suave pequeno">Buscando…</p>
          <div v-else-if="opcoes.length" style="display:grid;gap:.35rem;margin-top:.4rem;max-height:45vh;overflow:auto">
            <button v-for="(o, n) in opcoes" :key="n" type="button" class="escolha-opcao" style="width:100%;text-align:left" @click="escolher(o)">
              <span><strong>{{ o.descricao }}</strong><br>
                <span class="pequeno suave">AGHU <b class="mono">{{ o.codigo_aghu || '—' }}</b><template v-if="o.fornecedor"> · {{ o.fornecedor }}</template><template v-if="o.marca_fabricante"> · {{ o.marca_fabricante }}</template></span></span>
            </button>
          </div>
          <p v-else-if="buscou" class="pequeno suave">Nada encontrado.</p>
          <p class="pequeno suave" style="margin:.4rem 0 0">Não achou? Pode registrar só com lote e validade — o almoxarifado identifica o material pela etiqueta (ou pela foto).</p>
        </div>
        <div v-else class="aviso sucesso" style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap">
          <div style="flex:1 1 auto"><strong>{{ escolhido.descricao }}</strong><br>
            <span class="pequeno">AGHU <b class="mono">{{ escolhido.codigo_aghu || '—' }}</b><template v-if="escolhido.fornecedor"> · {{ escolhido.fornecedor }}</template></span></div>
          <button type="button" class="botao secundario pequeno" @click="trocar">Trocar</button>
        </div>
        <input type="hidden" name="xProd" :value="escolhido?.descricao || ''">
        <input type="hidden" name="codigo_aghu" :value="escolhido?.codigo_aghu || ''">
        <input type="hidden" name="marca_fabricante" :value="escolhido?.marca_fabricante || ''">
        <input v-if="escolhido?.fornecedor" type="hidden" name="fornecedor" :value="escolhido.fornecedor">

      <div class="grade grade-3" style="margin-top:.6rem">
        <div class="campo"><label class="obrigatorio">Lote</label>
          <input type="text" name="nLote" required :defaultValue="v.nLote || ''"></div>
        <div class="campo"><label class="obrigatorio">Validade</label>
          <input type="text" name="dVal" required placeholder="DD/MM/AAAA" :defaultValue="v.dVal || ''"></div>
        <div class="campo"><label class="obrigatorio">Quantidade usada</label>
          <input type="number" name="quantidade" min="1" max="20" :defaultValue="v.quantidade || 1" required></div>
        <div class="campo"><label class="obrigatorio">Por que não estava cadastrado?</label>
          <select name="motivo" required v-model="motivo">
            <option value="">— escolha —</option>
            <option v-for="m in d.motivos" :key="m">{{ m }}</option>
          </select></div>
        <div v-if="motivo === 'Outro'" class="campo"><label class="obrigatorio">Detalhe</label>
          <input type="text" name="detalhe" required :defaultValue="v.detalhe || ''"></div>
      </div>

      <h2 style="margin-top:1rem">Etiqueta</h2>
      <FotoEtiqueta @mudou="(t: boolean) => (temFoto = t)" />
      <label style="display:flex;gap:.6rem;align-items:center;margin:1rem 0;font-weight:600">
        <input type="checkbox" name="etiqueta_no_prontuario" value="1" :required="!temFoto" style="width:1.4rem;height:1.4rem"
               :defaultChecked="!!v.etiqueta_no_prontuario">
        A etiqueta do material foi colada no formulário de rastreabilidade.
        <span v-if="temFoto" class="pequeno suave" style="font-weight:400">(com a foto, é opcional)</span>
      </label>

      <button class="botao perigo" style="margin-top:.6rem">Registrar material não cadastrado</button>
    </form>

    <div v-if="d.registrados?.length" class="cartao">
      <h2>Já registrados neste atendimento</h2>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Material</th><th>Lote</th><th>Validade</th><th>Registrado</th><th>Situação</th></tr></thead>
        <tbody>
          <tr v-for="(r, n) in d.registrados" :key="n"><td>{{ r.xProd }}<template v-if="r.foto"><br><a class="pequeno" href="#" @click.prevent="fotoAberta = fotoAberta === r.foto ? '' : r.foto">ver foto da etiqueta</a>
              <ImagemApi v-if="fotoAberta === r.foto" :src="`/sala-procedimento/nao-cadastrado/foto/${r.foto}`" alt="foto" style="display:block;max-width:320px;margin-top:.3rem" /></template></td><td class="mono">{{ r.nLote }}</td><td class="pequeno">{{ f.dataBr(r.dVal) }}</td>
            <td class="pequeno">{{ f.dataHoraBr(r.registrado_em) }} · {{ r.registrado_por }} </td>
            <td><span v-if="r.situacao === 'pendente'" class="etiqueta amarelo">aguardando o almoxarifado</span>
                <span v-else class="etiqueta verde">regularizado</span></td></tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue';
import { useTela } from '../../composables/useTela';
import FotoEtiqueta from '../../components/opme/FotoEtiqueta.vue';
import ImagemApi from '../../components/opme/ImagemApi.vue';

const temFoto = ref(false);
const SEM_IDENTIFICACAO = 'MATERIAL NÃO IDENTIFICADO (ver etiqueta)';
const fotoAberta = ref('');
const props = defineProps<{ d: any }>();
const { f, getJson } = useTela();
const at = computed(() => props.d.atendimento);
const v = computed(() => props.d.dados || {});

// nov/2026: pesquisa pelo nome; na volta de um erro, reaproveita o que foi digitado.
const escolhido = ref<any>(v.value.xProd && v.value.xProd !== SEM_IDENTIFICACAO
  ? { descricao: v.value.xProd, codigo_aghu: v.value.codigo_aghu || '', fornecedor: v.value.fornecedor || '',
      marca_fabricante: v.value.marca_fabricante || '' } : null);
const motivo = ref<string>(v.value.motivo || '');
const busca = ref('');
const opcoes = ref<any[]>([]);
const buscando = ref(false);
const buscou = ref(false);
const campoBusca = ref<HTMLInputElement | null>(null);
let espera: ReturnType<typeof setTimeout> | undefined;
let seq = 0;
function digitando() {
  clearTimeout(espera);
  if (busca.value.trim().length < 3) { opcoes.value = []; buscou.value = false; return; }
  espera = setTimeout(pesquisar, 300);
}
async function pesquisar() {
  const meu = ++seq;
  buscando.value = true;
  try {
    const r: any = await getJson('/api/sala-procedimento/nao-cadastrado/buscar', { q: busca.value.trim() });
    if (meu !== seq) return;
    opcoes.value = r.itens || [];
    buscou.value = true;
  } catch {
    if (meu === seq) opcoes.value = [];
  } finally {
    if (meu === seq) buscando.value = false;
  }
}
function escolher(o: any) { escolhido.value = o; opcoes.value = []; }
async function trocar() { escolhido.value = null; busca.value = ''; buscou.value = false; await nextTick(); campoBusca.value?.focus(); }
onMounted(() => { if (!escolhido.value) campoBusca.value?.focus(); });
</script>
