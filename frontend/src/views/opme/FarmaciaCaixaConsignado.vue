<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Caixa <span class="mono">{{ cx.id_caixa }}</span></h1>
        <p>{{ cx.nome }} · fornecedor {{ cx.fornecedor || '—' }} · <strong>{{ cx.total }}</strong> item(ns) dentro</p>
      </div>
      <div class="acoes">
        <a class="botao secundario" :href="`${base}/${cx.id_caixa}/etiqueta`">Etiqueta da caixa</a>
        <a class="botao secundario" :href="base">Voltar</a>
      </div>
    </div>

    <!-- nov/2026: caixa montada no almoxarifado e dispensada à farmácia -->
    <div v-if="d.local === 'almoxarifado' && d.modo === 'almoxarifado'" class="cartao">
      <h2>No almoxarifado</h2>
      <p class="pequeno" style="margin-top:0">Monte a caixa bipando os itens do estoque do almoxarifado. Quando estiver pronta,
         dispense para a farmácia — ela dá ciência ao receber e, a partir daí, completa a caixa e envia para as salas.</p>
      <form method="post" :action="`${base}/${cx.id_caixa}/enviar`" class="filtros"
            :data-confirmar="`Dispensar a caixa ${cx.id_caixa} com ${cx.total} item(ns) para a farmácia?`">
        <div class="campo" style="flex:1 1 240px"><label class="obrigatorio">Farmácia de destino</label>
          <select name="farmacia" required>
            <option value="">Selecione…</option>
            <option v-for="(rot, chave) in d.farmacias" :key="chave" :value="chave">{{ rotulo(rot, chave) }}</option>
          </select></div>
        <button class="botao" :disabled="!cx.total">Dispensar para a farmácia</button>
      </form>
    </div>
    <div v-else-if="d.local === 'transito'" class="cartao" style="border-left:4px solid #b7791f">
      <h2>A caminho da farmácia {{ d.farmacia_rotulo }}</h2>
      <p class="pequeno" style="margin-top:0">Dispensada em {{ f.dataHoraBr(cx.enviada_em) }} por {{ cx.enviada_por }}.
         Aguardando a farmácia dar ciência do recebimento.</p>
      <form v-if="d.modo === 'farmacia'" method="post" :action="`${base}/${cx.id_caixa}/receber`"
            data-confirmar="Confirmar que a caixa chegou na farmácia?">
        <button class="botao">Dar ciência — caixa recebida</button>
      </form>
      <form v-else method="post" :action="`${base}/${cx.id_caixa}/cancelar-envio`" class="filtros"
            data-confirmar="Cancelar o envio? A caixa volta para o almoxarifado.">
        <div class="campo" style="flex:1 1 240px"><label class="obrigatorio">Motivo</label>
          <input type="text" name="motivo" required placeholder="Ex.: farmácia errada"></div>
        <button class="botao secundario">Cancelar envio</button>
      </form>
    </div>
    <div v-else-if="d.somente_leitura" class="cartao alerta-entrega-cartao">
      <p style="margin:0"><strong>{{ d.motivo_leitura }}</strong>
        <template v-if="d.farmacia_rotulo"> ({{ d.farmacia_rotulo }})</template></p>
    </div>

    <form v-if="cx.bloqueada && !d.somente_leitura" method="post" :action="`${base}/${cx.id_caixa}/conferir`"
          class="cartao alerta-entrega-cartao" data-confirmar="Confirmar a conferência e liberar a caixa?">
      <h2>Caixa BLOQUEADA — conferência</h2>
      <p><strong>{{ cx.bloqueio_motivo }}</strong><br>
         <span class="pequeno">Bloqueada em {{ f.dataHoraBr(cx.bloqueada_em) }} por {{ cx.bloqueada_por }}
         <template v-if="cx.bloqueio_prontuario">· prontuário {{ cx.bloqueio_prontuario }}, sala {{ cx.bloqueio_sala }}</template>.</span></p>
      <p class="pequeno">Conte fisicamente. Marque abaixo, na lista de itens, os que <strong>não estão</strong> na caixa
         (vão para divergência). Se a diferença foi um uso não bipado, a sala ainda pode bipar o uso naquele
         atendimento antes de você liberar.</p>
      <div class="campo"><label class="obrigatorio">O que foi conferido</label>
        <input type="text" name="motivo" required placeholder="Ex.: contagem física com 15 itens; 2 usados sem bip no prontuário 1048231"></div>
      <!-- Os checkboxes ficam na tabela; na hora de liberar, vão junto com este formulário. -->
      <input v-for="id in faltantes" :key="id" type="hidden" name="faltantes" :value="id">
      <button class="botao perigo">Conferida — liberar a caixa</button>
    </form>

    <div v-if="d.escolha?.length && d.lote_nao_encontrado" id="caixa-lote-nao-encontrado" class="cartao"
         style="border:3px solid var(--vermelho, #b3261e);background:#fdecea">
      <h2 style="color:var(--vermelho, #b3261e)">Lote bipado não encontrado</h2>
      <p>Não há no estoque nenhuma unidade com o lote <strong class="mono">{{ d.lote_nao_encontrado }}</strong> da etiqueta.
         <strong>Nada entrou na caixa.</strong> Confira a embalagem. Se o material for mesmo um destes outros lotes, clique nele:</p>
      <div style="display:grid;gap:.5rem">
        <form v-for="(g, n) in d.escolha" :key="g.id_unidade" method="post" :action="`${base}/${cx.id_caixa}/adicionar`" style="margin:0">
          <input type="hidden" name="id_unidade" :value="g.id_unidade">
          <button class="escolha-opcao" style="width:100%">
            <span class="escolha-num">{{ n + 1 }}</span>
            <span class="escolha-texto">
              <span class="escolha-produto">{{ g.descritivo_hospital || g.xProd }}</span>
              <span class="escolha-dados">AGHU <b class="mono">{{ g.codigo_aghu || '—' }}</b> · lote <b class="mono">{{ g.nLote || '—' }}</b> · val. {{ f.dataBr(g.dVal) || '—' }}</span>
              <span class="escolha-forn">{{ g.quantidade }} disponível(is) em estoque · {{ g.fornecedor || '' }}</span>
            </span>
          </button>
        </form>
      </div>
      <p style="margin:.6rem 0 0"><a :href="`${base}/${cx.id_caixa}`">Não é nenhum destes — voltar</a></p>
    </div>
    <div v-else-if="d.escolha?.length" class="cartao" style="border:3px solid #d18f00;background:var(--amarelo-claro)">
      <h2 style="color:#8a5a00">ATENÇÃO! Escolha o item</h2>
      <p>“<span class="mono">{{ d.codigo_digitado }}</span>” corresponde a {{ d.escolha.length }} materiais/lotes diferentes.
         Verifique o lote e a validade na embalagem e clique no certo.</p>
      <div style="display:grid;gap:.5rem">
        <form v-for="(g, n) in d.escolha" :key="g.id_unidade" method="post" :action="`${base}/${cx.id_caixa}/adicionar`" style="margin:0">
          <input type="hidden" name="id_unidade" :value="g.id_unidade">
          <button class="escolha-opcao" style="width:100%">
            <span class="escolha-num">{{ n + 1 }}</span>
            <span class="escolha-texto">
              <span class="escolha-produto">{{ g.descritivo_hospital || g.xProd }}</span>
              <span class="escolha-dados">AGHU <b class="mono">{{ g.codigo_aghu || '—' }}</b> · lote <b class="mono">{{ g.nLote || '—' }}</b> · val. {{ f.dataBr(g.dVal) || '—' }} · marca {{ g.marca_fabricante || '—' }}</span>
              <span class="escolha-forn">{{ g.quantidade }} disponível(is) em estoque · {{ g.fornecedor || '' }}</span>
            </span>
          </button>
        </form>
      </div>
      <p style="margin:.6rem 0 0"><a :href="`${base}/${cx.id_caixa}`" @click.prevent="emit('recarregar')">Cancelar</a></p>
    </div>

    <form v-if="!d.somente_leitura" method="post" :action="`${base}/${cx.id_caixa}/adicionar`" class="cartao">
      <h2>Colocar item na caixa</h2>
      <div class="filtros">
        <div class="campo" style="flex:1 1 280px"><label>Bipe o código de barras do item (ou digite o código AGHU)</label>
          <input type="text" name="codigo" ref="campoCodigo" autocomplete="off" placeholder="aguardando leitura…"></div>
        <div class="campo" style="width:9.5rem"><label title="Várias unidades iguais (mesmo lote) num bip só">Unidades por bip</label>
          <input type="number" name="quantidade" min="1" max="200" :defaultValue="1"></div>
        <button class="botao">Colocar na caixa</button>
      </div>
      <p class="suave pequeno" style="margin:.4rem 0 0"><template v-if="d.local === 'almoxarifado'">Entra só item do estoque do almoxarifado. </template>Entra só item em estoque, fora de outra caixa e dentro da validade.
         Para colocar 5 iguais do mesmo lote, ponha 5 em “Unidades por bip” e bipe uma vez.</p>
    </form>

    <!-- v18.11.7: o que entrou desde que a caixa foi aberta fica destacado até "Concluir" -->
    <div v-if="novos.length && !d.somente_leitura" id="colocados-agora" class="cartao"
         style="border:3px solid #1e9e5a;background:#eaf7ef">
      <div class="entre" style="gap:1rem;flex-wrap:wrap">
        <h2 style="margin:0;color:#14693c">Colocados agora: {{ novos.length }} item(ns)</h2>
        <button type="button" class="botao" @click="concluir">Concluir a caixa</button>
      </div>
      <div class="tabela-rolagem" style="margin-top:.6rem">
        <table>
          <thead><tr><th>Produto</th><th>AGHU</th><th>Lote</th><th>Validade</th><th>Entrou em</th></tr></thead>
          <tbody>
            <tr v-for="i in novos" :key="i.id_unidade">
              <td>{{ i.descritivo_hospital || i.xProd }}</td><td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td>
              <td class="mono">{{ i.nLote || '—' }}</td><td>{{ f.dataBr(i.dVal) || '—' }}</td>
              <td class="pequeno">{{ f.dataHoraBr(i.entrou_em) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="pequeno suave" style="margin:.4rem 0 0">Ao concluir, eles passam a aparecer só na lista normal da caixa.</p>
    </div>

    <div v-if="d.resumo?.length" class="cartao">
      <h2>Conteúdo por material e lote</h2>
      <p class="suave pequeno" style="margin-top:0">É a lista para conferir de olho — e a contagem que a sala vai informar na devolução.</p>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Material</th><th>AGHU</th><th>Lote</th><th>Validade</th><th class="num">Qtd.</th></tr></thead>
          <tbody>
            <tr v-for="(r, n) in d.resumo" :key="n" :style="novosPorLote(r) ? 'background:#eaf7ef' : ''"><td>{{ r.produto }}
                <span v-if="novosPorLote(r)" class="etiqueta verde" style="margin-left:.3rem">+{{ novosPorLote(r) }} agora</span></td><td class="mono pequeno">{{ r.codigo_aghu || '—' }}</td>
                <td class="mono">{{ r.nLote || '—' }}</td><td>{{ f.dataBr(r.dVal) || '—' }}</td>
                <td class="num"><strong>{{ r.quantidade }}</strong></td></tr>
            <tr><td colspan="4"><strong>Total na caixa</strong></td><td class="num"><strong>{{ cx.total }}</strong></td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="cartao">
      <h2>{{ d.itens.length }} item(ns) na caixa</h2>
      <div v-if="d.itens.length" class="tabela-rolagem">
        <table>
          <thead><tr><th v-if="cx.bloqueada">Não está</th><th>Produto</th><th>AGHU</th><th>Lote</th><th>Validade</th><th>Entrou em</th><th v-if="!d.somente_leitura">Retirar</th></tr></thead>
          <tbody>
            <tr v-for="i in d.itens" :key="i.id_unidade" :style="idsNovos.has(i.id_unidade) ? 'background:#eaf7ef' : ''">
              <td v-if="cx.bloqueada"><input type="checkbox" :value="i.id_unidade" v-model="faltantes" style="width:auto"></td>
              <td>{{ i.descritivo_hospital || i.xProd }}
                <span v-if="idsNovos.has(i.id_unidade)" class="etiqueta verde" style="margin-left:.3rem">novo</span></td>
              <td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td>
              <td class="mono">{{ i.nLote || '—' }}</td>
              <td>{{ f.dataBr(i.dVal) || '—' }}</td>
              <td class="pequeno">{{ f.dataHoraBr(i.entrou_em) }}</td>
              <td v-if="!d.somente_leitura">
                <form method="post" :action="`${base}/${cx.id_caixa}/retirar/${i.id_unidade}`" style="display:flex;gap:.4rem;margin:0">
                  <input type="text" name="motivo" placeholder="motivo (opcional)" style="width:150px">
                  <button class="botao secundario pequeno">Retirar</button>
                </form>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Caixa vazia. Bipe os itens acima.</p>
    </div>

    <a ref="linkLista" :href="base" style="display:none">lista</a>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const emit = defineEmits<{ (e: 'recarregar'): void }>();
const { f } = useTela();
const cx = computed(() => props.d.caixa);
const base = computed(() => props.d.base || '/farmacia/caixas-consignado');
function rotulo(rot: any, chave: any) { return typeof rot === 'string' ? rot : (rot?.rotulo || rot?.nome || String(chave)); }
const faltantes = ref<string[]>([]);
const campoCodigo = ref<HTMLInputElement | null>(null);
onMounted(() => { if (!props.d.escolha?.length) campoCodigo.value?.focus(); });

// v18.11.7: "foto" do que estava na caixa ao abrir (botão Abrir da lista). O que entrou
// depois aparece destacado até a pessoa clicar em "Concluir a caixa".
const chave = computed(() => `traceopme-caixa-aberta:${cx.value?.id_caixa}`);
const foto = ref<Set<string> | null>(null);
function lerFoto() {
  const ids = (props.d.itens || []).map((i: any) => i.id_unidade);
  let abrir = false;
  try { abrir = new URLSearchParams(window.location.search).get('abrir') === '1'; } catch { /* sem URL */ }
  try {
    const salvo = abrir ? null : sessionStorage.getItem(chave.value);
    if (salvo) { foto.value = new Set(JSON.parse(salvo)); return; }
    sessionStorage.setItem(chave.value, JSON.stringify(ids));
  } catch { /* sem armazenamento: nada destacado */ }
  foto.value = new Set(ids);
}
lerFoto();
const novos = computed(() => (props.d.itens || []).filter((i: any) => foto.value && !foto.value.has(i.id_unidade)));
const idsNovos = computed(() => new Set(novos.value.map((i: any) => i.id_unidade)));
function novosPorLote(r: any) {
  return novos.value.filter((i: any) => String(i.codigo_aghu || '') === String(r.codigo_aghu || '')
    && String(i.nLote || '').toUpperCase() === String(r.nLote || '').toUpperCase()).length;
}
const linkLista = ref<HTMLAnchorElement | null>(null);
function concluir() {
  try { sessionStorage.removeItem(chave.value); } catch { /* ok */ }
  linkLista.value?.click();
}
</script>
