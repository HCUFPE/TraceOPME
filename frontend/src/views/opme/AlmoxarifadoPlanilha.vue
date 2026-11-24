<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Planilha de lotes do AGHU</h1>
        <p>Importe a planilha e bipe o material. Cada item só entra no estoque quando for bipado.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/almoxarifado">Voltar</a></div>
    </div>

    <div class="grade grade-2">
      <form method="post" action="/almoxarifado/planilha" enctype="multipart/form-data" class="cartao">
        <h2>Importar planilha</h2>
        <p class="pequeno suave">Colunas: cod_material, material, marca_comercial, lote, serie, data_validade,
          qtde_disponivel_lote (CSV separado por ponto e vírgula, como sai do AGHU). Descrição = material;
          fornecedor = marca comercial. Reimportar a mesma planilha não duplica.</p>
        <input type="file" name="arquivo" accept=".csv,.txt,.xlsx" required>
        <button class="botao" style="margin-top:.6rem">Importar</button>
      </form>
      <div class="cartao">
        <h2>Pendente de bipar</h2>
        <div class="numero" style="font-size:2rem;font-weight:700">{{ d.total_pendente }}</div>
        <p class="rotulo">unidade(s) em {{ d.itens.length }} lote(s)</p>
        <details v-if="d.cargas?.length" style="margin-top:.4rem"><summary class="pequeno" style="cursor:pointer">Planilhas importadas ({{ d.cargas.length }})</summary>
          <ul class="pequeno lista" style="margin:.4rem 0 0 1rem">
            <li v-for="(c, n) in d.cargas" :key="n">{{ f.dataHoraBr(c.criado_em) }} · {{ c.arquivo || 'planilha' }} · {{ c.linhas }} lote(s), {{ c.unidades }} unid. ·
              <strong>{{ c.pendentes }}</strong> pendente(s) · {{ c.criado_por }}</li>
          </ul>
        </details>
      </div>
    </div>

    <div v-if="itens.length" class="cartao">
      <h2>Dar entrada: escolha o material e bipe</h2>
      <p class="pequeno suave" style="margin-top:0">1. Encontre o material na lista · 2. clique em <strong>Bipar</strong> ·
        3. informe a quantidade e bipe o código de barras da embalagem. Só entra no estoque o que for bipado.</p>
      <div style="display:flex;gap:.8rem;align-items:flex-end;flex-wrap:wrap;margin-bottom:.6rem">
        <div class="campo" style="margin:0;flex:1 1 24rem">
          <label for="filtro-planilha">Buscar material (AGHU, descrição, lote ou marca)</label>
          <input type="search" id="filtro-planilha" ref="campoFiltro" v-model="filtro" autocomplete="off"
                 placeholder="ex.: 97941 · shaver · razek" style="width:100%;font-size:1.05rem;padding:.6rem .7rem"
                 @keydown.enter.prevent>
        </div>
        <span class="pequeno suave" id="filtro-contagem">{{ termos.length ? `${visiveis.length} lote(s) encontrado(s)` : '' }}</span>
      </div>
      <div class="tabela-rolagem">
        <table id="tabela-planilha">
          <thead><tr><th>AGHU</th><th>Material</th><th>Marca</th><th>Lote</th><th>Validade</th>
            <th class="num">Pendente</th><th></th></tr></thead>
          <tbody>
            <template v-for="i in visiveis" :key="i.id_item">
              <tr :style="aberto === i.id_item ? 'outline:3px solid var(--azul, #0c3a67)' : ''">
                <td class="mono pequeno">{{ i.codigo_aghu }}</td>
                <td class="pequeno">{{ i.material }}<template v-if="i.codigo_barras"><br><span class="suave mono">cód. {{ i.codigo_barras }}</span></template></td>
                <td class="pequeno">{{ i.marca || '—' }}</td>
                <td class="mono pequeno">{{ i.lote || '—' }}</td>
                <td class="pequeno">{{ i.validade }}</td>
                <td class="num"><strong class="pendente">{{ i.qtd_pendente }}</strong><span class="suave"> / {{ i.qtd_total }}</span></td>
                <td style="white-space:nowrap;text-align:right">
                  <button type="button" class="botao pequeno" @click="abrir(i)">Bipar</button>
                  <details style="display:inline-block;text-align:left"><summary class="pequeno" style="cursor:pointer">mais</summary>
                    <form method="post" :action="`/almoxarifado/planilha/${i.id_item}/sem-codigo`" style="margin:.4rem 0;display:flex;gap:.3rem;align-items:center">
                      <input type="number" name="quantidade" min="1" :max="i.qtd_pendente" :defaultValue="i.qtd_pendente" style="width:5rem">
                      <select name="tipo_entrada" style="width:auto">
                        <option v-for="(rotulo, chave) in d.tipos" :key="chave" :value="chave" :selected="String(chave) === 'aquisicao_propria'">{{ rotulo }}</option>
                      </select>
                      <button class="botao secundario pequeno">sem código de barras → etiqueta</button>
                    </form>
                    <form method="post" :action="`/almoxarifado/planilha/${i.id_item}/retirar`" style="display:flex;gap:.3rem;align-items:center">
                      <input type="text" name="motivo" required minlength="3" placeholder="motivo" style="width:11rem">
                      <button class="botao secundario pequeno">retirar da lista</button>
                    </form>
                  </details>
                </td>
              </tr>
              <tr v-if="aberto === i.id_item" class="painel-bip">
                <td colspan="7" style="background:var(--azul-claro, #e8f1fb);border-left:5px solid var(--azul, #0c3a67);padding:1rem">
                  <div style="font-size:.85rem;font-weight:700;letter-spacing:.04em;color:var(--azul, #0c3a67)">MATERIAL ESCOLHIDO</div>
                  <div style="font-size:1.15rem;font-weight:700;margin:.15rem 0">{{ i.material }}</div>
                  <div class="pequeno" style="margin-bottom:.7rem">
                    AGHU <strong>{{ i.codigo_aghu }}</strong> · marca <strong>{{ i.marca || '—' }}</strong> · lote
                    <strong>{{ i.lote || '—' }}</strong> · validade <strong>{{ i.validade }}</strong> · pendente
                    <strong>{{ i.qtd_pendente }}</strong>
                    <template v-if="i.codigo_barras"> · código já conhecido <span class="mono">{{ i.codigo_barras }}</span></template>
                  </div>
                  <div style="display:flex;gap:.8rem;align-items:flex-end;flex-wrap:wrap">
                    <div class="campo" style="margin:0;flex:0 0 9rem">
                      <label>Quantidade</label>
                      <input type="number" v-model.number="qtd" min="1" :max="i.qtd_pendente" style="font-size:1.3rem;padding:.6rem"
                             @keydown.enter.prevent="campoCodigo?.focus()">
                    </div>
                    <div class="campo" style="margin:0;flex:0 0 13rem">
                      <label>Classificação <span class="opcional">(padrão: aquisição própria)</span></label>
                      <select v-model="tipo" style="font-size:1.05rem;padding:.6rem">
                        <option v-for="(rotulo, chave) in d.tipos" :key="chave" :value="chave">{{ rotulo }}</option>
                      </select>
                    </div>
                    <div class="campo" style="margin:0;flex:1 1 20rem">
                      <label>Bipe o código de barras da embalagem</label>
                      <input type="text" ref="campoCodigo" v-model="codigo" autocomplete="off" placeholder="aguardando leitura…"
                             style="font-size:1.3rem;padding:.6rem;text-align:center" @keydown.enter.prevent="bipar(i)">
                    </div>
                    <button type="button" class="botao secundario" title="Gera o código interno (AGHU + lote) e abre a etiqueta"
                            @click="semCodigo(i)">Sem código de barras: gerar</button>
                    <button type="button" class="botao secundario" @click="fechar">Fechar</button>
                  </div>
                  <div class="pequeno" style="margin-top:.6rem;font-weight:600" :style="{ color: resultado?.ok ? 'var(--verde)' : 'var(--vermelho)' }">
                    <template v-if="resultado">
                      {{ resultado.ok ? '✔' : '✖' }} {{ resultado.mensagem }}
                      <span v-for="(a, n) in resultado.alertas || []" :key="n" style="color:var(--amarelo)"><br>⚠ {{ a }}</span>
                    </template>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
    <div v-else class="cartao"><p class="vazio">Nenhum item pendente. Importe uma planilha para começar.</p></div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, postJson, acao } = useTela();

const itens = ref<any[]>((props.d.itens || []).map((i: any) => ({ ...i, concluido: false })));
const filtro = ref('');
const aberto = ref<number | null>(null);
const qtd = ref(1);
const tipo = ref('aquisicao_propria');
const codigo = ref('');
const resultado = ref<any>(null);
const campoFiltro = ref<HTMLInputElement | null>(null);
const campoCodigo = ref<HTMLInputElement | null>(null);

function norm(t: unknown) {
  return String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase()
    .replace(/[.,;:()/\-]+/g, ' ').replace(/\s+/g, ' ').trim();
}
const termos = computed(() => norm(filtro.value).split(' ').filter(Boolean));
const visiveis = computed(() => itens.value.filter((i) => {
  if (i.concluido) return false;
  const texto = norm(`${i.codigo_aghu} ${i.material} ${i.marca} ${i.lote} ${i.codigo_barras || ''}`);
  return termos.value.every((t) => texto.includes(t));
}));

function som(freq: number) {
  try {
    const c = new (window.AudioContext || (window as any).webkitAudioContext)();
    const o = c.createOscillator();
    o.frequency.value = freq; o.connect(c.destination); o.start(); o.stop(c.currentTime + 0.12);
  } catch { /* som é acessório */ }
}

async function abrir(i: any) {
  aberto.value = i.id_item;
  qtd.value = 1;
  tipo.value = 'aquisicao_propria';
  codigo.value = '';
  resultado.value = null;
  await nextTick();
  campoCodigo.value?.focus();
}

function fechar() {
  aberto.value = null;
  resultado.value = null;
  campoFiltro.value?.focus();
}

async function bipar(i: any) {
  const c = codigo.value.trim();
  codigo.value = '';
  if (!c) return;
  try {
    const r: any = await postJson('/almoxarifado/planilha/bipar', {
      codigo: c, id_item: i.id_item, quantidade: qtd.value || 1, tipo_entrada: tipo.value,
    });
    resultado.value = r;
    if (r.ok) {
      som(880);
      i.qtd_pendente = r.restante;
      i.codigo_barras = i.codigo_barras || c;
      qtd.value = 1;
      if (r.restante <= 0) {
        setTimeout(() => { i.concluido = true; fechar(); }, 1500);
      }
    } else {
      som(200);
    }
  } catch {
    resultado.value = { ok: false, mensagem: 'Falha de conexão — bipe de novo.' };
  } finally {
    campoCodigo.value?.focus();
  }
}

function semCodigo(i: any) {
  const n = Number(qtd.value) || 1;
  if (!confirm(`Gerar o código interno e dar entrada em ${n} unidade(s) deste lote? Em seguida abre a etiqueta para imprimir.`)) return;
  acao(`/almoxarifado/planilha/${i.id_item}/sem-codigo`, { quantidade: n, tipo_entrada: tipo.value });
}

onMounted(() => campoFiltro.value?.focus());
</script>
