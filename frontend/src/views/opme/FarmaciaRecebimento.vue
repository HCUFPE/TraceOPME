<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1 v-if="rem.status === 'cancelada'">{{ transferencia ? 'Transferência cancelada' : devolucao ? 'Devolução cancelada' : 'Envio cancelado' }}</h1>
        <h1 v-else-if="transferencia">{{ rem.status === 'conferida' ? 'Ciência da transferência registrada' : `Transferência da ${rem.farmacia_origem_rotulo} — conferir e dar ciência` }}</h1>
        <h1 v-else-if="devolucao">{{ rem.status === 'conferida' ? 'Ciência da devolução registrada' : `Devolução da ${rem.farmacia_rotulo} — conferir e dar ciência` }}</h1>
        <h1 v-else>{{ rem.status === 'conferida' ? 'Ciência do envio registrada' : 'Envio do almoxarifado — conferir e dar ciência' }}</h1>
        <p><strong v-if="transferencia">{{ rem.farmacia_origem_rotulo }} → </strong><strong>{{ rem.farmacia_rotulo }}</strong> · <span class="mono">{{ rem.id_remessa }}</span> · {{ transferencia ? 'transferido' : devolucao ? 'devolvido' : 'enviado' }} por
          {{ rem.enviada_por || rem.criado_por }} em {{ f.dataHoraBr(rem.enviada_em || rem.criado_em) }}
          <template v-if="rem.observacao"> · {{ rem.observacao }}</template>
          <template v-if="rem.status === 'conferida'"> · ciência de <span class="etiqueta verde">{{ rem.conferida_nome }}</span> em {{ f.dataHoraBr(rem.conferida_em) }}</template></p>
      </div>
      <div class="acoes"><a class="botao secundario" :href="rotas.voltar">Voltar</a></div>
    </div>

    <div v-if="rem.status === 'aberta'" class="aviso info">{{ devolucao ? 'A farmácia ainda está montando esta devolução.' : 'O almoxarifado ainda está montando este envio.' }}</div>
    <div v-else-if="rem.status === 'cancelada'" class="aviso alerta"><strong>Cancelado</strong> por {{ rem.cancelada_por }} em
      {{ f.dataHoraBr(rem.cancelada_em) }} — motivo: {{ rem.motivo_cancelamento }}. Nada a conferir.</div>
    <form v-else-if="rem.status === 'enviada' && rem.pendentes?.length" method="post" :action="rotas.conferir"
          class="cartao" id="form-receb" @submit="confirmarFaltas">
      <h2>1. Confira o material ({{ pendentes.length }})</h2>
      <div style="display:flex;gap:1.2rem;flex-wrap:wrap;margin:.3rem 0 .6rem">
        <label style="display:flex;gap:.4rem;align-items:center;font-weight:600">
          <input type="radio" name="modo" value="lista" v-model="modo" style="width:auto"> Conferir pela lista</label>
        <label style="display:flex;gap:.4rem;align-items:center;font-weight:600">
          <input type="radio" name="modo" value="bipando" v-model="modo" style="width:auto"> Conferir bipando o material</label>
      </div>
      <p v-if="modo === 'lista'" class="pequeno suave" id="ajuda-lista">Tudo vem marcado. <strong>Desmarque o que não chegou</strong> e clique em
        <strong>Dar ciência</strong> — o que ficar desmarcado vira pendência, sinalizada para tratativa.</p>
      <div v-else id="bloco-bip">
        <p class="pequeno suave">Bipe cada material que chegou. Cada bip marca o item. O que <strong>não</strong> for bipado fica
          como pendência do envio, sinalizada para tratativa.</p>
        <!-- v18.21: vários iguais com o mesmo código — diga quantos e bipe uma vez só -->
        <div style="display:flex;gap:1rem;align-items:flex-end;flex-wrap:wrap">
          <div style="flex:1 1 18rem;min-width:14rem">
            <label for="bip-receb">Bipe o código de barras</label>
            <input type="text" id="bip-receb" ref="campoBip" v-model="codigo" autocomplete="off" placeholder="aguardando leitura…"
                   style="font-size:1.4rem;padding:.7rem;text-align:center" @keydown.enter.prevent="bipar">
          </div>
          <div style="width:9.5rem">
            <label for="qtd-bipe">Quantidade</label>
            <input type="number" id="qtd-bipe" v-model.number="qtdPorBipe" min="1" :max="pendentes.length"
                   data-sem-foco="1" style="font-size:1.4rem;padding:.7rem;text-align:center">
          </div>
        </div>
        <p class="pequeno suave" style="margin:.35rem 0 0">São 5 iguais, com o mesmo código? Escreva
          <strong>5</strong> na quantidade e bipe <strong>uma vez</strong> — o sistema marca as 5.
          A quantidade volta para 1 depois de cada leitura, para não marcar demais sem querer.</p>
        <div style="display:flex;gap:1rem;align-items:center;margin:.5rem 0 .8rem;flex-wrap:wrap">
          <span class="etiqueta azul" style="font-size:1rem"><span id="bip-contagem">{{ bipados.length }}</span> de {{ pendentes.length }} bipado(s)</span>
          <!-- v18.35 -->
          <span v-if="falhaAoSalvar" class="etiqueta vermelho pequeno">⚠ {{ falhaAoSalvar }}</span>
          <span v-else-if="bipados.length" class="pequeno suave">o que já foi bipado fica guardado — dá para parar e continuar depois</span>
          <span class="pequeno" :style="{ color: resultado.ok ? 'var(--verde)' : 'var(--vermelho)' }">{{ resultado.texto }}</span>
        </div>
      </div>
      <!-- v18.20: mesma estrutura da tela de estoque — uma linha por material/lote, com quantidade -->
      <template v-if="modo === 'lista'">
        <div class="tabela-rolagem"><table>
          <thead><tr><th style="width:9rem">Recebido?</th><th>AGHU</th><th>Material</th><th>Lote</th>
            <th>Validade</th><th>Fornecedor / marca</th><th class="num">Qtd.</th></tr></thead>
          <tbody>
            <tr v-for="g in grupos" :key="g.chave">
              <td>
                <label v-if="g.itens.length === 1" style="display:flex;gap:.45rem;align-items:center">
                  <input type="checkbox" :checked="quantos[g.chave] > 0" style="width:1.4rem;height:1.4rem"
                         @change="quantos[g.chave] = ($event.target as HTMLInputElement).checked ? 1 : 0">
                  <span class="pequeno">chegou</span></label>
                <div v-else style="display:flex;gap:.4rem;align-items:center">
                  <input type="number" min="0" :max="g.itens.length" v-model.number="quantos[g.chave]"
                         style="width:4.2rem;text-align:center">
                  <span class="pequeno suave">de {{ g.itens.length }}</span>
                </div>
              </td>
              <td class="mono">{{ g.codigo_aghu || '—' }}</td>
              <td>{{ g.descricao }}<br><span class="mono pequeno suave">{{ g.codigo_barras || '' }}</span></td>
              <td class="mono">{{ g.nLote || '—' }}</td>
              <td>{{ g.validade }}</td>
              <td class="pequeno">{{ g.fornecedor || '—' }}<template v-if="g.marca_fabricante"><br><span class="suave">{{ g.marca_fabricante }}</span></template></td>
              <td class="num"><strong>{{ g.itens.length }}</strong></td>
            </tr>
          </tbody>
        </table></div>
        <p class="pequeno suave" style="margin:.5rem 0 0">Selecionados: <strong>{{ recebidos.length }}</strong>
          de {{ pendentes.length }}<template v-if="recebidos.length < pendentes.length">
          — {{ pendentes.length - recebidos.length }} vira(m) pendência</template>.</p>
      </template>

      <!-- v18.20: bipando, o que falta fica em cima e diminui a cada leitura -->
      <template v-else>
        <h3 style="margin:.8rem 0 .3rem">Falta bipar ({{ pendentes.length - bipados.length }})</h3>
        <p v-if="!gruposFaltam.length" class="aviso sucesso" style="margin:.2rem 0">Tudo bipado. Pode dar ciência.</p>
        <div v-else class="tabela-rolagem"><table>
          <thead><tr><th class="num" style="width:5rem">Falta</th><th>AGHU</th><th>Material</th><th>Lote</th>
            <th>Validade</th><th>Fornecedor / marca</th></tr></thead>
          <tbody>
            <tr v-for="g in gruposFaltam" :key="g.chave">
              <td class="num"><strong>{{ g.faltam }}</strong><template v-if="g.itens.length > 1" >
                <br><span class="pequeno suave">de {{ g.itens.length }}</span></template></td>
              <td class="mono">{{ g.codigo_aghu || '—' }}</td>
              <td>{{ g.descricao }}<br><span class="mono pequeno suave">{{ g.codigo_barras || '' }}</span></td>
              <td class="mono">{{ g.nLote || '—' }}</td>
              <td>{{ g.validade }}</td>
              <td class="pequeno">{{ g.fornecedor || '—' }}<template v-if="g.marca_fabricante"><br><span class="suave">{{ g.marca_fabricante }}</span></template></td>
            </tr>
          </tbody>
        </table></div>
        <details v-if="bipados.length" style="margin-top:.8rem">
          <summary class="pequeno">Já bipados ({{ bipados.length }}) — clique para ver</summary>
          <div class="tabela-rolagem" style="margin-top:.4rem"><table>
            <thead><tr><th class="num" style="width:5rem">Qtd.</th><th>AGHU</th><th>Material</th><th>Lote</th><th>Validade</th></tr></thead>
            <tbody>
              <tr v-for="g in gruposBipados" :key="g.chave">
                <td class="num"><strong>{{ g.bipados }}</strong></td>
                <td class="mono">{{ g.codigo_aghu || '—' }}</td>
                <td class="pequeno">{{ g.descricao }}</td>
                <td class="mono">{{ g.nLote || '—' }}</td>
                <td class="pequeno">{{ g.validade }}</td>
              </tr>
            </tbody>
          </table></div>
        </details>
      </template>
      <input v-for="id in recebidos" :key="`r${id}`" type="hidden" name="recebido" :value="id">
      <input v-for="id in bipados" :key="id" type="hidden" name="bipado" :value="id">
      <h2 style="margin-top:1.2rem">2. Dar ciência</h2>
      <p class="pequeno">Fica registrado em nome de <strong>{{ auth.user?.nome }}</strong> (usuário logado).</p>
      <div class="campo" style="max-width:32rem"><label>Observação <span class="opcional">(opcional)</span></label>
        <input type="text" name="observacao"></div>
      <button class="botao">Dar ciência do recebimento</button>
    </form>

    <div v-if="resolvidos.length" class="cartao">
      <h2>Resultado</h2>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Situação</th><th>Material</th><th>AGHU</th><th>Lote</th><th></th></tr></thead>
        <tbody>
          <tr v-for="i in resolvidos" :key="i.id_item">
            <td>
              <span v-if="i.situacao === 'cancelado'" class="etiqueta cinza">cancelado</span>
              <span v-else-if="i.situacao === 'recebido'" class="etiqueta verde">recebido<template v-if="i.tratativa"> depois</template></span>
              <span v-else-if="i.tratativa" class="etiqueta cinza">{{ d.tratativas[i.tratativa] }}</span>
              <span v-else class="etiqueta vermelho">não recebido — pendência</span>
            </td>
            <td class="pequeno">{{ i.descricao }}</td><td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td>
            <td class="mono pequeno">{{ i.nLote || '—' }}</td>
            <td><form v-if="i.situacao === 'nao_recebido' && !i.tratativa" method="post" :action="rotas.recebi.replace('{id}', String(i.id_item))" style="margin:0">
                <input type="hidden" name="voltar" :value="rotas.pagina">
                <button class="botao secundario pequeno">recebi</button></form></td>
          </tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, auth, getJson, postJson } = useTela();
const rem = computed(() => props.d.rem);
// nov/2026: a mesma tela serve à farmácia (envio do almoxarifado) e ao almoxarifado (devolução da farmácia).
const devolucao = computed(() => rem.value?.sentido === 'farmacia_almox');
const transferencia = computed(() => rem.value?.sentido === 'farmacia_farmacia');
const rotas = computed(() => props.d.rotas || {
  identificar: `/farmacia/recebimento/${rem.value.id_remessa}/identificar`,
  conferir: `/farmacia/recebimento/${rem.value.id_remessa}/conferir`,
  recebi: '/farmacia/recebimento/item/{id}/recebi', pagina: `/farmacia/recebimento/${rem.value.id_remessa}`,
  voltar: '/farmacia/recebimentos',
});
const pendentes = computed(() => [...(rem.value.pendentes || [])].sort((a: any, b: any) => a.id_item - b.id_item));
const resolvidos = computed(() => (rem.value.itens || []).filter((i: any) => i.situacao !== 'pendente')
  .sort((a: any, b: any) => a.id_item - b.id_item));
const modo = ref<'lista' | 'bipando'>('lista');

// v18.20: a conferência passou a ser por material/lote, como a tela de estoque.
// Antes, um envio de 6 unidades do mesmo cateter virava 6 linhas idênticas de
// duas linhas de texto cada — e, bipando, a lista inteira ficava parada na tela
// sem mostrar o que ainda faltava.
function chaveDo(i: any) {
  return [i.codigo_aghu, i.descricao, i.nLote, i.validade, i.fornecedor, i.marca_fabricante].join('|');
}
function agrupar(itens: any[]) {
  const mapa = new Map<string, any>();
  for (const i of itens) {
    const chave = chaveDo(i);
    if (!mapa.has(chave)) {
      mapa.set(chave, {
        chave, itens: [], codigo_aghu: i.codigo_aghu, descricao: i.descricao, nLote: i.nLote,
        validade: i.validade, fornecedor: i.fornecedor, marca_fabricante: i.marca_fabricante,
        codigo_barras: i.codigo_barras,
      });
    }
    mapa.get(chave).itens.push(i);
  }
  return [...mapa.values()].sort((a, b) => (a.descricao || '').localeCompare(b.descricao || '')
    || String(a.nLote).localeCompare(String(b.nLote)));
}
const grupos = computed(() => agrupar(pendentes.value));
// quantas unidades de cada grupo chegaram (começa com tudo, como antes)
const quantos = reactive<Record<string, number>>({});
watch(grupos, (gs) => { for (const g of gs) if (quantos[g.chave] === undefined) quantos[g.chave] = g.itens.length; },
      { immediate: true });
const recebidos = computed<string[]>(() => grupos.value.flatMap(
  (g) => g.itens.slice(0, Math.max(0, Math.min(quantos[g.chave] ?? g.itens.length, g.itens.length)))
                .map((i: any) => String(i.id_item))));
const gruposFaltam = computed(() => agrupar(pendentes.value.filter((i: any) => !bipados.value.includes(String(i.id_item))))
  .map((g) => ({ ...g, faltam: g.itens.length })));
const gruposBipados = computed(() => agrupar(pendentes.value.filter((i: any) => bipados.value.includes(String(i.id_item))))
  .map((g) => ({ ...g, bipados: g.itens.length })));
// v18.35: a conferência é gravada no servidor a cada bipe. Ao abrir a tela,
// volta exatamente de onde parou — mesmo em outro computador ou com outra
// pessoa continuando.
const bipados = ref<string[]>([...(props.d.conferidos || [])].map(String));
watch(() => props.d.conferidos, (c) => { bipados.value = [...(c || [])].map(String); });
const salvando = ref(false);
const falhaAoSalvar = ref('');

async function guardar(ids: string[], marcar = true) {
  if (!rotas.value.marcar) return true;            // servidor antigo: segue como era
  salvando.value = true;
  try {
    const corpo = new FormData();
    for (const id of ids) corpo.append('id_item', id);
    corpo.append('marcar', marcar ? '1' : '0');
    const r: any = await postJson(rotas.value.marcar, corpo);
    falhaAoSalvar.value = r?.ok ? '' : (r?.mensagem || 'não foi possível guardar este bipe');
    return !!r?.ok;
  } catch {
    falhaAoSalvar.value = 'sem conexão com o servidor — este bipe pode não ter sido guardado';
    return false;
  } finally {
    salvando.value = false;
  }
}
const codigo = ref('');
const qtdPorBipe = ref(1);
const resultado = ref<{ ok: boolean; texto: string }>({ ok: true, texto: '' });
const campoBip = ref<HTMLInputElement | null>(null);

watch(modo, async (m) => { if (m === 'bipando') { await nextTick(); campoBip.value?.focus(); } });

async function bipar() {
  const c = codigo.value.trim();
  codigo.value = '';
  if (!c) return;
  // v18.21: uma leitura pode valer por várias unidades iguais do mesmo código.
  const pedidos = Math.max(1, Math.floor(qtdPorBipe.value || 1));
  try {
    const r: any = await getJson(rotas.value.identificar, { codigo: c });
    const livres: string[] = r.ok
      ? (r.itens || []).map(String).filter((id: string) => !bipados.value.includes(id))
      : [];
    const marcar = livres.slice(0, pedidos);
    if (marcar.length) {
      bipados.value.push(...marcar);
      await guardar(marcar, true);
      // v18.20: diz o que acabou de entrar e quanto falta — com lista grande,
      // o código sozinho não ajudava a acompanhar.
      const item: any = pendentes.value.find((i: any) => String(i.id_item) === marcar[0]);
      const nome = item ? `${item.descricao} · lote ${item.nLote || '—'}` : c;
      const faltam = pendentes.value.length - bipados.value.length;
      const sobrou = pedidos > marcar.length
        ? ` Só havia ${marcar.length} deste código ainda não bipado(s).` : '';
      resultado.value = { ok: true, texto:
        `✔ ${marcar.length > 1 ? `${marcar.length} × ` : ''}${nome} — recebido${marcar.length > 1 ? 's' : ''}.`
        + `${sobrou} ${faltam ? `Faltam ${faltam}.` : 'Tudo bipado.'}` };
    } else {
      resultado.value = { ok: false, texto: r.ok ? `✖ ${c} — já bipado.` : `✖ ${r.mensagem}` };
    }
  } catch {
    resultado.value = { ok: false, texto: 'Falha de conexão — bipe de novo.' };
  }
  qtdPorBipe.value = 1;
  campoBip.value?.focus();
}

function confirmarFaltas(evento: Event) {
  const b = modo.value === 'bipando';
  const qtd = b ? bipados.value.length : recebidos.value.length;
  const faltam = pendentes.value.length - qtd;
  if (faltam > 0 && !confirm(`${faltam} item(ns) ${b ? 'não foram bipados' : 'foram desmarcados'} e ficarão como pendência (não recebidos). Dar ciência assim mesmo?`)) {
    evento.preventDefault();
  }
}
</script>
