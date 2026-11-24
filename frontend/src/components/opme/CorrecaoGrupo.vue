<template>
  <div class="cartao" style="border-left:5px solid var(--azul);margin-bottom:1rem">
    <div class="entre" style="align-items:flex-start;flex-wrap:nowrap">
      <div style="flex:1;min-width:0">
        <h2 style="margin-bottom:.2rem">Corrigir {{ g.quantidade }} unidades de uma vez</h2>
        <p class="suave pequeno" style="margin:0">
          <strong>{{ g.xProd }}</strong> · lote {{ g.nLote || '—' }} ·
          val. {{ f.dataBr(g.dVal) || '—' }} · código {{ g.codigo_barras || '—' }}<br>
          <template v-if="!temMisto">Estas unidades foram cadastradas com exatamente os mesmos dados. Mude só
            o que está errado — o resto fica como está.</template>
          <template v-else><strong>Mesmo lote, cadastrado de jeitos diferentes.</strong>
            Os campos marcados abaixo estão divergentes e vêm vazios: preencha para igualar as
            {{ g.quantidade }} unidades, ou deixe em branco para cada uma ficar como está.</template>
        </p>
      </div>
      <div style="text-align:right;flex:0 0 auto">
        <div class="numero">{{ g.quantidade }}</div>
        <div class="rotulo">unidades</div>
      </div>
    </div>

    <!-- Correção em lote: a contagem de unidades marcadas acompanha as caixinhas,
         no botão e na pergunta de confirmação. -->
    <form method="post" action="/almoxarifado/correcoes-lote" style="margin-top:1rem"
          :data-confirmar="`Aplicar esta correção a ${marcadas.length} unidade(s)? Cada uma fica registrada no próprio histórico.`">
      <input type="hidden" name="busca" :value="busca">
      <!-- O valor que a tela mostrou vai junto de cada campo: o servidor só aplica o que foi de fato mudado. -->
      <div class="grade grade-3">
        <div v-for="c in campos" :key="c.nome" class="campo">
          <label>{{ c.rotulo }}</label>
          <input v-if="c.nome === 'codigo_aghu'" :type="c.tipo" :name="c.nome" v-model="aghu">
          <input v-else :type="c.tipo" :name="c.nome" :defaultValue="c.valor"
                 :placeholder="g.misto?.[c.nome] ? 'valores diferentes — preencha para igualar' : ''">
          <input type="hidden" :name="`original_${c.nome}`" :value="c.valor">
          <!-- v18.17: o que está cadastrado hoje, quando o campo diverge entre as unidades -->
          <p v-if="g.misto?.[c.nome]" class="pequeno suave" style="margin:.25rem 0 0">
            hoje:
            <template v-for="(v, i) in g.misto[c.nome]" :key="i">
              <span v-if="i"> · </span><strong>{{ v.valor || '(vazio)' }}</strong> ({{ v.quantidade }})
            </template>
          </p>
          <DescritivoHc v-if="c.nome === 'codigo_aghu'" :codigo="aghu" />
        </div>
        <div class="campo">
          <label>Classificação</label>
          <select name="tipo_entrada" v-model="tipo">
            <option v-for="(nome, codigo) in tipos" :key="codigo" :value="codigo">{{ nome }}</option>
          </select>
          <input type="hidden" name="original_tipo_entrada" :value="g.tipo_entrada || ''">
        </div>
        <div v-if="tipo === 'consignado' || g.codigo_consignado" class="campo">
          <label :class="{ obrigatorio: tipo === 'consignado' }">Código consignado</label>
          <input type="text" name="codigo_consignado" :defaultValue="g.codigo_consignado || ''" :required="tipo === 'consignado'">
          <input type="hidden" name="original_codigo_consignado" :value="g.codigo_consignado || ''">
        </div>
      </div>
      <p class="pequeno suave" style="margin:.2rem 0 .8rem">
        O <strong>número de série</strong> não aparece aqui de propósito: ele é
        individual de cada unidade. Para corrigi-lo, use a correção uma a uma, abaixo.
      </p>

      <details style="margin-bottom:.8rem">
        <summary style="cursor:pointer" class="pequeno">
          Unidades incluídas: <strong>{{ marcadas.length }}</strong> de {{ g.quantidade }}
          — clique para ver e tirar alguma da correção
        </summary>
        <label class="pequeno" style="display:flex;gap:.4rem;align-items:center;margin:.6rem 0;font-weight:600">
          <input type="checkbox" :checked="marcadas.length === g.ids.length" style="width:auto" @change="marcarTodas"> marcar / desmarcar todas
        </label>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(11rem,1fr));gap:.3rem .8rem">
          <label v-for="id in g.ids" :key="id" class="mono pequeno" style="display:flex;gap:.35rem;align-items:center;font-weight:400">
            <input type="checkbox" name="ids" :value="id" v-model="marcadas" style="width:auto">
            {{ id }}
          </label>
        </div>
      </details>

      <div class="campo">
        <label class="obrigatorio">Motivo da correção</label>
        <input type="text" name="motivo" required placeholder="Ex.: validade digitada errada na entrada manual">
      </div>
      <button class="botao" :disabled="marcadas.length === 0">Corrigir as {{ marcadas.length }} unidades</button>
    </form>

    <!-- nov/2026: quantidade errada ou cadastro feito por engano. -->
    <details class="ajuste-cadastro" style="margin-top:1rem;border-top:1px solid var(--borda);padding-top:.8rem">
      <summary style="cursor:pointer"><strong>Quantidade errada ou cadastro feito por engano?</strong>
        <span class="suave pequeno"> — ajustar a quantidade ou excluir unidades</span></summary>
      <div class="grade grade-2" style="margin-top:.8rem;align-items:start">
        <form method="post" action="/almoxarifado/correcoes/quantidade" class="cartao" style="margin:0;box-shadow:none"
              :data-confirmar="`Ajustar a quantidade deste cadastro de ${g.quantidade} para ${quantidade || '?'} unidade(s)?`">
          <h3 style="margin-top:0">Corrigir a quantidade</h3>
          <input type="hidden" name="busca" :value="busca">
          <input v-for="id in g.ids" :key="'q' + id" type="hidden" name="ids" :value="id">
          <div class="campo">
            <label class="obrigatorio">Quantidade correta <span class="opcional">(hoje: {{ g.quantidade }})</span></label>
            <input type="number" name="quantidade" min="0" max="500" required v-model="quantidade" inputmode="numeric">
            <div class="dica">Para menos, saem as últimas unidades cadastradas (só se ainda não se movimentaram).
              Para mais, entram unidades com os mesmos dados (só cadastro manual).</div>
          </div>
          <div class="campo">
            <label class="obrigatorio">Motivo</label>
            <input type="text" name="motivo" required minlength="5" placeholder="Ex.: digitei 10, eram 8">
          </div>
          <button class="botao secundario">Ajustar quantidade</button>
        </form>
        <form method="post" action="/almoxarifado/correcoes/excluir" class="cartao" style="margin:0;box-shadow:none;border-left:5px solid var(--vermelho)"
              :data-confirmar="`Excluir do estoque as ${marcadas.length} unidade(s) marcada(s)? O registro continua no histórico de cada uma, com o motivo.`">
          <h3 style="margin-top:0">Excluir cadastro errado</h3>
          <input type="hidden" name="busca" :value="busca">
          <input v-for="id in marcadas" :key="'x' + id" type="hidden" name="ids" :value="id">
          <p class="pequeno suave" style="margin-top:0">Exclui as <strong>{{ marcadas.length }}</strong> unidade(s) marcada(s) acima
            (em “Unidades incluídas”). Só sai o que ainda está parado no almoxarifado, sem nenhuma movimentação.
            Se veio por NF, a unidade volta a ficar pendente na nota para receber de novo.</p>
          <div class="campo">
            <label class="obrigatorio">Motivo da exclusão</label>
            <input type="text" name="motivo" required minlength="5" placeholder="Ex.: cadastrado no produto errado">
          </div>
          <button class="botao perigo" :disabled="marcadas.length === 0">Excluir as {{ marcadas.length }} unidade(s)</button>
        </form>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import DescritivoHc from './DescritivoHc.vue';
import { useFormatos } from '../../utils/formatos';

const props = defineProps<{ g: any; busca: string; tipos: Record<string, string> }>();
const f = useFormatos();
const marcadas = ref<string[]>([...(props.g.ids || [])]);
const aghu = ref(props.g.codigo_aghu || '');
const tipo = ref(props.g.tipo_entrada || 'aquisicao_propria');
const quantidade = ref<string | number>('');
const temMisto = computed(() => Object.keys(props.g.misto || {}).length > 0);
const campos = computed(() => [
  { nome: 'xProd', rotulo: 'Descrição', tipo: 'text', valor: props.g.xProd || '' },
  { nome: 'codigo_barras', rotulo: 'Código de barras', tipo: 'text', valor: props.g.codigo_barras || '' },
  { nome: 'codigo_aghu', rotulo: 'Código AGHU', tipo: 'text', valor: props.g.codigo_aghu || '' },
  { nome: 'marca_fabricante', rotulo: 'Marca/Fabricante', tipo: 'text', valor: props.g.marca_fabricante || '' },
  { nome: 'fornecedor', rotulo: 'Fornecedor', tipo: 'text', valor: props.g.fornecedor || '' },
  { nome: 'nLote', rotulo: 'Lote', tipo: 'text', valor: props.g.nLote || '' },
  { nome: 'dFab', rotulo: 'Fabricação', tipo: 'date', valor: props.g.dFab || '' },
  { nome: 'dVal', rotulo: 'Validade', tipo: 'date', valor: props.g.dVal || '' },
  { nome: 'vUnCom', rotulo: 'Valor unitário', tipo: 'text', valor: props.g.vUnCom || 0 },
]);

function marcarTodas(e: Event) {
  marcadas.value = (e.target as HTMLInputElement).checked ? [...props.g.ids] : [];
}
</script>
