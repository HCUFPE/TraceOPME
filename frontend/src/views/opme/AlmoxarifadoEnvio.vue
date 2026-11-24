<template>
  <div>
    <div class="cabecalho-pagina nao-imprimir">
      <div>
        <h1>{{ tx.titulo }}</h1>
        <p class="mono pequeno">{{ rem.id_remessa }} · aberto por {{ rem.criado_por }} em {{ f.dataHoraBr(rem.criado_em) }}
          <template v-if="rem.enviada_em"> · {{ tx.enviado }} por {{ rem.enviada_por }} em {{ f.dataHoraBr(rem.enviada_em) }}</template></p>
      </div>
      <div class="acoes">
        <button v-if="rem.status !== 'aberta'" type="button" class="botao secundario" @click="imprimir">Imprimir romaneio</button>
        <a class="botao secundario" :href="rotas.voltar">Voltar</a>
      </div>
    </div>

    <template v-if="rem.status === 'aberta'">
      <div class="bipagem nao-imprimir">
        <div class="cartao" style="border:2px solid var(--azul, #0c3a67)">
          <p v-if="transferencia" style="margin:0 0 .8rem">Transferindo da <strong>{{ rem.farmacia_origem_rotulo }}</strong> para a
            <strong>{{ rem.farmacia_rotulo }}</strong>. <a :href="rotas.trocar" data-sem-foco="1">voltar</a></p>
          <p v-else-if="devolucao" style="margin:0 0 .8rem">Devolvendo da <strong>{{ rem.farmacia_rotulo }}</strong> para o
            <strong>almoxarifado</strong>. <a :href="rotas.trocar" data-sem-foco="1">trocar de farmácia</a></p>
          <p v-else style="margin:0 0 .8rem">Enviando para a <strong>{{ rem.farmacia_rotulo }}</strong>.
            <a :href="rotas.trocar" data-sem-foco="1">trocar de farmácia</a></p>
          <form method="post" :action="rotas.finalizar"
                style="margin:0 0 1rem;padding-bottom:1rem;border-bottom:1px solid var(--borda, #d9dee5)"
                :data-confirmar="tx.confirmarFinalizar">
            <div class="linha-botoes">
              <button class="botao" data-sem-foco="1">Finalizar {{ tx.doc }} ({{ lista.length }} item(ns))</button>
              <label class="pequeno" style="display:flex;align-items:center;gap:.4rem;font-weight:400">
                <input type="checkbox" id="som" v-model="som" data-sem-foco="1" style="width:auto"> som de confirmação</label>
            </div>
            <details style="margin-top:.5rem"><summary class="pequeno" style="cursor:pointer">Observação <span class="suave">(se precisar)</span></summary>
              <input type="text" name="observacao" placeholder="Ex.: reposição semanal" data-sem-foco="1" style="margin-top:.4rem"></details>
          </form>
          <div style="display:flex;gap:.8rem;align-items:flex-end;flex-wrap:wrap">
            <div class="campo" style="margin:0;flex:1 1 320px">
              <label for="codigo">Bipe o código de barras</label>
              <input type="text" id="codigo" ref="campo" v-model="codigo" autocomplete="off" autocapitalize="off" spellcheck="false"
                     placeholder="aguardando leitura…" :disabled="travado" @keydown.enter.prevent="ler" @input="conf?.fecharSeVerde()">
            </div>
            <!-- v18.11: caixa fechada do mesmo item — várias unidades do mesmo lote num bip só -->
            <div class="campo" style="margin:0;width:9.5rem">
              <label for="qtd-envio" title="Para caixa fechada: quantas unidades do MESMO lote vão com este bip">Unidades por bip</label>
              <input type="number" id="qtd-envio" v-model.number="qtd" min="1" max="500" data-sem-foco="1"
                     :style="qtd > 1 ? 'font-weight:700;border:2px solid var(--azul, #0c3a67);background:#eef4fb' : ''"
                     @change="focar()">
            </div>
          </div>
          <p v-if="qtd > 1" id="aviso-qtd" class="pequeno" style="margin:.35rem 0 0;color:var(--azul, #0c3a67);font-weight:600">
            O próximo bip leva {{ qtd }} unidades do mesmo lote (depois volta para 1).</p>
          <!-- v18.11: o resultado do bip fica logo abaixo do campo -->
          <ResultadoLeitura ref="resultado" />
          <div v-if="naoRegistrado" id="ultimo-nao-registrado" class="pequeno" style="margin-top:.4rem;color:var(--vermelho, #b3261e);font-weight:600">
            Última leitura NÃO registrada: {{ naoRegistrado }}
          </div>
                    <div v-if="escolha" id="envio-escolha" style="margin-top:.8rem" :class="['aviso', escolha.lote_nao_encontrado ? 'erro' : 'alerta']">
            <strong>{{ escolha.mensagem }}</strong>
            <table style="margin-top:.4rem"><tbody>
              <tr v-for="(o, n) in escolha.opcoes" :key="n">
                <td class="mono pequeno">{{ o.aghu }}</td><td class="pequeno">{{ o.descricao }}</td>
                <td class="mono pequeno">lote {{ o.lote }}</td><td class="pequeno">{{ o.validade }}</td>
                <td class="num">{{ o.disponivel }} disp.</td>
                <td><button type="button" class="botao pequeno" data-sem-foco="1" @click="enviar(escolha.codigo, o.grupo)">é este</button></td>
              </tr>
            </tbody></table>
          </div>

          <div v-if="lista.length" class="aviso info" id="lista-envio-bloco" style="margin-top:1rem">
            <strong>{{ tx.naLista }}</strong> <span id="envio-contagem">{{ lista.length }} item(ns)</span>
            <span class="pequeno suave">— o último bipado fica em cima.</span>
            <table style="margin-top:.6rem"><tbody id="lista-envio">
              <!-- v18.12: unidades iguais (mesmo AGHU e lote) numa linha só, com a quantidade -->
              <tr v-for="g in listaAgrupada" :key="g.itens[0].id_item">
                <td class="pequeno"><strong v-if="g.itens.length > 1" class="qtd-grupo">{{ g.itens.length }}×</strong>
                  <span class="mono"><strong>AGHU {{ g.itens[0].aghu }}</strong></span> · {{ g.itens[0].descricao }}<br>
                  <span class="mono suave">lote {{ g.itens[0].lote }} · val. {{ g.itens[0].validade }}</span></td>
                <td class="pequeno suave">{{ g.itens[0].quando }} · {{ g.itens[0].por }}</td>
                <td style="text-align:right"><button type="button" class="botao secundario pequeno" data-sem-foco="1"
                    @click="tirar(g.itens[0].id_item)">{{ g.itens.length > 1 ? 'tirar 1' : 'tirar' }}</button></td>
              </tr>
            </tbody></table>
          </div>

        </div>

        <div class="cartao">
          <h2>Consultar antes de bipar</h2>
          <p class="suave pequeno">Há <strong>{{ d.disponiveis_total }}</strong> item(ns) disponíveis no
            {{ tx.origem }}.
            Use a busca se precisar conferir se algo está disponível.</p>
          <form method="get" :action="rotas.pagina">
            <label for="busca-estoque" class="pequeno"><strong>Código AGHU, descrição, lote ou código de barras</strong></label>
            <input type="text" id="busca-estoque" name="busca" :defaultValue="d.busca" data-sem-foco="1" placeholder="ex.: 23265 ou introdutor">
            <button class="botao secundario pequeno" style="margin-top:.4rem" data-sem-foco="1">Buscar</button>
          </form>
          <template v-if="d.busca">
            <ul v-if="d.resultados?.length" class="pequeno" style="margin:.6rem 0 0 1rem;padding:0;list-style:disc">
              <li v-for="(r, n) in d.resultados" :key="n" style="margin-bottom:.4rem"><span class="mono">AGHU {{ r.codigo_aghu || '—' }}</span> · {{ r.descricao }}<br>
                <span class="suave">lote {{ r.nLote || '—' }} · val. {{ r.validade }} · <strong>{{ r.quantidade }}</strong> disp.</span></li>
            </ul>
            <p v-else class="pequeno" style="margin-top:.6rem;color:var(--vermelho, #b3261e)">Nada disponível {{ tx.nadaEm }} com “{{ d.busca }}”.</p>
          </template>
        </div>
      </div>
      <AvisoValidade v-if="avisoValidade" :aviso="avisoValidade" :enviando="enviandoCiencia" @ciente="cienteValidade" @cancelar="cancelarValidade" />
    <ConfirmacaoBip ref="conf" :dica-falha="`Este material NÃO foi para ${tx.aDoc}. Clique em OK para continuar.`"
                      :tempo-ok="2000" @fechou="aoFecharConfirmacao" />
    </template>

    <div v-if="rem.status === 'enviada'" class="aviso info nao-imprimir">
      {{ tx.finalizado }}</div>
    <div v-else-if="rem.status === 'conferida'" class="aviso sucesso nao-imprimir">Conferido por <strong>{{ rem.conferida_nome }}</strong> em {{ f.dataHoraBr(rem.conferida_em) }}
      ({{ rem.modo_conferencia === 'bipando' ? 'bipando' : 'pela lista' }}).</div>
    <div v-else-if="rem.status === 'cancelada'" class="aviso alerta nao-imprimir">
      <strong>{{ tx.cancelado }}</strong> por {{ rem.cancelada_por }} em {{ f.dataHoraBr(rem.cancelada_em) }}
      — motivo: {{ rem.motivo_cancelamento }}. Os itens voltaram ao {{ tx.origem }}.</div>

    <!-- nov/2026: quem enviou cancela enquanto o outro lado não deu ciência. -->
    <details v-if="rem.status === 'aberta' || rem.status === 'enviada'" class="cartao nao-imprimir" id="cancelar-envio"
             style="border-left:5px solid var(--vermelho, #b3261e)">
      <summary style="cursor:pointer;font-weight:600">Cancelar {{ tx.esteDoc }}</summary>
      <p class="pequeno" style="margin:.5rem 0">
        {{ tx.enquanto }}
        Todos os itens voltam ao {{ tx.origem }} e o cancelamento fica no histórico de cada item.</p>
      <form method="post" :action="rotas.cancelar" style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:flex-end"
            :data-confirmar="`Cancelar ${tx.aDoc} ${rem.id_remessa}? Os itens voltam ao estoque de origem.`">
        <div class="campo" style="margin:0;flex:1;min-width:16rem"><label for="motivo-cancelar">Motivo</label>
          <input type="text" id="motivo-cancelar" name="motivo" required minlength="3" data-sem-foco="1"
                 placeholder="ex.: enviado para a farmácia errada"></div>
        <button class="botao perigo" data-sem-foco="1">Cancelar {{ tx.doc }}</button>
      </form>
    </details>

    <div v-if="rem.status !== 'aberta'" class="cartao">
      <h2 class="so-imprimir">{{ tx.romaneio }}</h2>
      <p class="so-imprimir pequeno">Enviado por {{ rem.enviada_por || rem.criado_por }} em {{ f.dataHoraBr(rem.enviada_em || rem.criado_em) }}<template v-if="rem.observacao"> · {{ rem.observacao }}</template></p>
      <h2 class="nao-imprimir">Itens {{ tx.daDoc }} ({{ rem.itens.length }})</h2>
      <div v-if="rem.itens.length" class="tabela-rolagem"><table>
        <thead><tr><th>AGHU</th><th>Material</th><th>Lote</th><th>Validade</th><th>Situação</th></tr></thead>
        <tbody>
          <tr v-for="i in rem.itens" :key="i.id_item">
            <td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td>
            <td class="pequeno">{{ i.descricao }}</td>
            <td class="mono pequeno">{{ i.nLote || '—' }}</td>
            <td class="pequeno">{{ i.validade }}</td>
            <td class="pequeno">
              <template v-if="i.situacao === 'pendente'">{{ tx.aguardando }}</template>
              <span v-else-if="i.situacao === 'cancelado'" class="etiqueta cinza">cancelado (voltou à origem)</span>
              <span v-else-if="i.situacao === 'recebido'" class="etiqueta verde">recebido<template v-if="i.tratativa"> depois</template></span>
              <span v-else-if="i.tratativa" class="etiqueta cinza">{{ d.tratativas[i.tratativa] }}</span>
              <span v-else class="etiqueta vermelho">não recebido</span>
            </td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhum item bipado ainda.</p>
      <div class="so-imprimir" style="margin-top:2rem">
        <p>{{ tx.assinaEnvia }}: ________________________ &nbsp;&nbsp;
          Recebido por ({{ tx.assinaRecebe }}): ________________________ &nbsp;&nbsp; Data: ___/___/_____</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue';
import AvisoValidade from '../../components/opme/AvisoValidade.vue';
import ConfirmacaoBip from '../../components/opme/ConfirmacaoBip.vue';
import ResultadoLeitura from '../../components/opme/ResultadoLeitura.vue';
import { useLeitor } from '../../composables/useLeitor';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, postJson } = useTela();
const rem = computed(() => props.d.rem);
// nov/2026: a mesma tela monta o envio (almoxarifado → farmácia) e a devolução (farmácia → almoxarifado).
const devolucao = computed(() => rem.value?.sentido === 'farmacia_almox');
// v18: e a transferência entre farmácias (Bloco ↔ Hemodinâmica).
const transferencia = computed(() => rem.value?.sentido === 'farmacia_farmacia');
const tx = computed(() => {
  const r = rem.value || {};
  const dest = r.farmacia_rotulo, orig = r.farmacia_origem_rotulo;
  if (transferencia.value) return {
    titulo: `Transferência da ${orig} para a ${dest}`, enviado: 'transferido', doc: 'transferência', aDoc: 'a transferência',
    esteDoc: 'esta transferência', daDoc: 'da transferência', origem: `estoque da ${orig}`, nadaEm: 'nesta farmácia',
    confirmarFinalizar: `Finalizar a transferência para a ${dest}? Depois disso a ${dest} confere e dá ciência.`,
    vaiPara: `para a ${dest}`, cadaBip: `Cada bip tira do estoque da ${orig} na hora (“em trânsito para a farmácia”).`,
    naLista: `Na transferência para a ${dest}:`, finalizado: `Transferência finalizada — aguardando a ciência da ${dest}.`,
    cancelado: 'Transferência cancelada',
    enquanto: `Enquanto a ${dest} não der ciência, a ${orig} pode cancelar a transferência.`,
    romaneio: `Romaneio de transferência ${r.id_remessa} — ${orig} → ${dest}`, aguardando: `aguardando a ${dest}`,
    assinaEnvia: `Enviado por (${orig})`, assinaRecebe: dest, confirmacao: 'NA TRANSFERÊNCIA', paraQuem: dest,
  };
  if (devolucao.value) return {
    titulo: `Devolução da ${dest} para o almoxarifado`, enviado: 'devolvido', doc: 'devolução', aDoc: 'a devolução',
    esteDoc: 'esta devolução', daDoc: 'da devolução', origem: `estoque da ${dest}`, nadaEm: 'nesta farmácia',
    confirmarFinalizar: 'Finalizar a devolução para o almoxarifado? Depois disso o almoxarifado confere e dá ciência.',
    vaiPara: 'voltar para o almoxarifado', cadaBip: 'Cada bip tira do estoque da farmácia na hora (“em devolução para o almoxarifado”).',
    naLista: 'Na devolução para o almoxarifado:', finalizado: 'Devolução finalizada — aguardando a ciência do almoxarifado.',
    cancelado: 'Devolução cancelada', enquanto: 'Enquanto o almoxarifado não der ciência, a farmácia pode cancelar a devolução.',
    romaneio: `Romaneio de devolução ${r.id_remessa} — ${dest} → almoxarifado`, aguardando: 'aguardando o almoxarifado',
    assinaEnvia: 'Devolvido por (farmácia)', assinaRecebe: 'almoxarifado', confirmacao: 'NA DEVOLUÇÃO AO ALMOXARIFADO', paraQuem: 'almoxarifado',
  };
  return {
    titulo: `Envio para a ${dest}`, enviado: 'enviado', doc: 'envio', aDoc: 'o envio',
    esteDoc: 'este envio', daDoc: 'do envio', origem: 'estoque do almoxarifado', nadaEm: 'no almoxarifado',
    confirmarFinalizar: `Finalizar o envio para a ${dest}? Depois disso a farmácia confere e dá ciência.`,
    vaiPara: 'para a farmácia', cadaBip: 'Cada bip tira do estoque do almoxarifado na hora (“em trânsito para a farmácia”).',
    naLista: `No envio para a ${dest}:`, finalizado: `Envio finalizado — aguardando a conferência da ${dest}.`,
    cancelado: 'Envio cancelado', enquanto: 'Enquanto a farmácia não der ciência do recebimento, o almoxarifado pode cancelar o envio.',
    romaneio: `Romaneio de envio ${r.id_remessa} — ${dest}`, aguardando: 'aguardando a farmácia',
    assinaEnvia: 'Enviado por', assinaRecebe: 'farmácia', confirmacao: 'ENVIADO PARA A FARMÁCIA', paraQuem: dest,
  };
});
const rotas = computed(() => props.d.rotas || {
  pagina: `/almoxarifado/envio/${rem.value.id_remessa}`, bipar: `/almoxarifado/envio/${rem.value.id_remessa}/bipar`,
  tirar: '/almoxarifado/envio/item/{id}/tirar', finalizar: `/almoxarifado/envio/${rem.value.id_remessa}/finalizar`,
  cancelar: `/almoxarifado/envio/${rem.value.id_remessa}/cancelar`, voltar: '/almoxarifado/envios', trocar: '/almoxarifado/envios',
});

const campo = ref<HTMLInputElement | null>(null);
const resultado = ref<InstanceType<typeof ResultadoLeitura> | null>(null);
const conf = ref<InstanceType<typeof ConfirmacaoBip> | null>(null);
const som = ref(true);
const codigo = ref('');
const lista = ref<any[]>([...(props.d.lista || [])]);
const listaAgrupada = computed(() => {
  const grupos: { chave: string; itens: any[] }[] = [];
  for (const i of lista.value) {
    const chave = `${i.aghu}|${String(i.lote || '').toUpperCase()}|${i.validade}|${i.descricao}`;
    const g = grupos.find((x) => x.chave === chave);
    if (g) g.itens.push(i); else grupos.push({ chave, itens: [i] });
  }
  return grupos;
});
const naoRegistrado = ref('');
const escolha = ref<any>(null);
const travado = ref(false);
const qtd = ref(1);
const { bip, focar, bloquear } = useLeitor(campo, { somLigado: som });

function ler() {
  const c = codigo.value.trim();
  codigo.value = '';
  if (c) enviar(c);
}

async function enviar(cod: string, grupo = '', cienciaValidade = false) {
  try {
    const dd: any = await postJson(rotas.value.bipar,
      { codigo: cod, quantidade: Math.max(1, Math.floor(Number(qtd.value) || 1)), grupo, ciencia_validade: cienciaValidade });
    escolha.value = null;
    if (dd.aviso_validade) {
      // nov/2026: há lote que vence antes — pede ciência (não trava). Nada saiu ainda.
      bip(660, 0.15); setTimeout(() => bip(660, 0.15), 220);
      avisoValidade.value = dd;
      travar(true);
      resultado.value?.personalizado({ classe: '', estilo: 'background:var(--amarelo-claro)', icone: '!',
        titulo: 'Aguardando a ciência', detalhe: 'Há lote do mesmo material que vence antes.' });
      return;
    }
    if (dd.ok) {
      bip(880);
      naoRegistrado.value = '';
      const det = `${dd.quantidade > 1 ? dd.quantidade + ' unidades · ' : ''}AGHU ${dd.item.aghu} · lote ${dd.item.lote} · validade ${dd.item.validade}`;
      qtd.value = 1;
      resultado.value?.mostrar(true, dd.item.descricao, det);
      conf.value?.mostrar(true, tx.value.confirmacao, dd.item.descricao, `${det}\n${tx.value.paraQuem}`);
      lista.value = dd.lista || [];
    } else if (dd.escolher) {
      bip(440);
      resultado.value?.limpar();
      escolha.value = dd;
    } else {
      bip(200, 0.3);
      naoRegistrado.value = cod;
      resultado.value?.mostrar(false, dd.titulo || 'Não foi possível registrar', dd.mensagem);
      travar(true);
      conf.value?.mostrar(false, dd.nao_cadastrado ? 'MATERIAL NÃO CADASTRADO' : 'NÃO REGISTRADO', `Código lido: ${cod}`, dd.mensagem);
    }
  } catch {
    resultado.value?.mostrar(false, 'Falha de conexão', 'Verifique a rede e bipe de novo.');
  } finally {
    focar();
  }
}

// ----------------------------------------------------------- aviso de validade (nov/2026)
const avisoValidade = ref<any>(null);
const enviandoCiencia = ref(false);
async function cienteValidade() {
  const a = avisoValidade.value;
  if (!a) return;
  enviandoCiencia.value = true;
  avisoValidade.value = null;
  travar(false);
  try {
    await enviar(a.codigo, a.grupo, true);
  } finally {
    enviandoCiencia.value = false;
  }
}
async function cancelarValidade() {
  avisoValidade.value = null;
  travar(false);
  resultado.value?.mostrar(false, 'Leitura cancelada', 'Nada foi enviado. Bipe o lote que vence antes.');
  await nextTick();
  focar();
}

function travar(sim: boolean) {
  travado.value = sim;
  bloquear(sim);
}

async function aoFecharConfirmacao(falha: boolean) {
  if (falha) travar(false);
  await nextTick();
  focar();
}

async function tirar(idItem: number) {
  const dd: any = await postJson(rotas.value.tirar.replace('{id}', String(idItem)), {});
  resultado.value?.mostrar(dd.ok, dd.ok ? 'Tirado' : 'Não foi possível tirar', dd.mensagem);
  if (dd.ok) lista.value = dd.lista || [];
  focar();
}

function imprimir() {
  window.print();
}
</script>

<style>
.so-imprimir { display: none; }
@media print { .so-imprimir { display: block !important; } }
.qtd-grupo { display: inline-block; min-width: 2.2rem; margin-right: .4rem; padding: .05rem .4rem; border-radius: 6px;
  background: var(--azul, #0c3a67); color: #fff; text-align: center; }
</style>
