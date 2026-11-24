<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Nota de consumo e RM (AGHU)</h1>
        <p>Prontuários com material usado no dia e tudo o que foi bipado em cada paciente, por código AGHU e por lote.
           Os botões abrem o robô <strong>neste computador</strong> (janela preta + navegador):
           <strong>Nota de consumo</strong> — você abre a cirurgia (Materiais Consumidos) e ele inclui material e quantidade;
           <strong>Requisição de material (RM)</strong> — você abre a RM e vincula o paciente, ele inclui os materiais e, na
           efetivação, marca o <strong>lote</strong> usado. Quem grava/efetiva é você.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" />

    <form method="get" action="/farmacia/nota-consumo" class="cartao filtros-nc">
      <div><label>Data do procedimento</label><input type="date" name="data" :defaultValue="d.data"></div>
      <label class="marcar"><input type="checkbox" name="pendentes" value="1" :defaultChecked="d.pendentes"> só os com algo a lançar</label>
      <button class="botao">Pesquisar</button>
      <span class="pequeno suave">{{ d.atendimentos.length }} prontuário(s) · nota de consumo lançada em {{ d.total_lancadas }} · RM em {{ d.total_rm }}</span>
    </form>

    <p class="pequeno suave" style="margin:-.3rem 0 .8rem">
      Primeira vez neste computador? <a href="/farmacia/robo-aghu/instalador" @click.prevent="baixar('/farmacia/robo-aghu/instalador')">Baixar
      o instalador do robô</a> — o mesmo da NF; se já está instalado aqui, não precisa de novo. Extraia numa pasta fixa e dê dois
      cliques em <strong>instalar.bat</strong> (uma vez). Se o Windows bloquear o .bat: na barra de endereço da pasta digite
      <strong>cmd</strong>, ENTER, e depois <strong>py instalar.py</strong>.</p>
    <p v-if="msgRobo" :class="['aviso', erroRobo ? 'erro' : 'info']">{{ msgRobo }}</p>

    <p v-if="!d.atendimentos.length" class="vazio cartao">Nenhum prontuário com material usado em {{ f.dataBr(d.data) }}
      <template v-if="d.unidade_atual"> na {{ f.rotuloUnidade(d.unidade_atual) }}</template>.</p>

    <div v-for="a in d.atendimentos" :key="a.id_atendimento" class="cartao pac">
      <div class="pac-topo">
        <div class="pac-id">
          <strong class="nome">{{ a.paciente || 'Paciente' }}</strong>
          <span class="mono">Pront. {{ a.prontuario }}</span>
          <span class="pequeno suave">{{ f.rotuloUnidade(a.unidade) }} · sala {{ a.sala || '—' }} · {{ a.especialidade || '—' }}
            <template v-if="a.hora_inicio"> · {{ a.hora_inicio }}</template></span>
        </div>
        <div class="docs">
          <div v-for="doc in DOCS" :key="doc.tipo" :class="['doc', 'st-' + (a[doc.tipo + '_status'] || 'pendente')]">
            <div class="doc-cab">
              <strong>{{ doc.nome }}</strong>
              <span :class="['etiqueta', a[doc.tipo + '_status'] === 'lancada' ? 'verde' : a[doc.tipo + '_status'] === 'em_lancamento' ? 'amarelo' : 'cinza']">
                {{ a[doc.tipo + '_rotulo'] }}</span>
            </div>
            <span v-if="a[doc.tipo + '_status'] === 'lancada'" class="pequeno suave">{{ f.dataHoraBr(a['aghu_' + doc.tipo + '_lancado_em']) }} · {{ a['aghu_' + doc.tipo + '_lancado_por'] }}</span>
            <span v-else-if="a[doc.tipo + '_status'] === 'em_lancamento'" class="pequeno suave">Robô chamado por {{ a['aghu_' + doc.tipo + '_iniciado_por'] }}.</span>
            <div class="doc-acoes">
              <button v-if="a[doc.tipo + '_status'] !== 'lancada'" type="button" class="botao pequeno" :disabled="chamando === a.id_atendimento + doc.tipo"
                      @click="lancar(a, doc.tipo)">
                {{ chamando === a.id_atendimento + doc.tipo ? 'Abrindo…' : a[doc.tipo + '_status'] === 'em_lancamento' ? 'Abrir o robô de novo' : 'Lançar no AGHU' }}</button>
              <form method="post" :action="`/farmacia/nota-consumo/${a.id_atendimento}/marcar`" style="margin:0">
                <input type="hidden" name="data" :value="d.data"><input type="hidden" name="tipo" :value="doc.tipo">
                <button v-if="a[doc.tipo + '_status'] !== 'lancada'" class="link-botao" name="acao" value="lancada">já lancei à mão</button>
                <button v-else class="link-botao" name="acao" value="desfazer" :data-confirmar="`Voltar ${doc.nome} para não lançada?`">desfazer</button>
              </form>
            </div>
          </div>
        </div>
      </div>
      <p v-if="!a.uso_finalizado_em && a.status === 'aberto'" class="pequeno" style="color:#8a5a00;margin:0 0 .4rem">A sala ainda não finalizou o registro de uso.</p>
      <!-- v18.12.2: a lista de materiais fica fechada (a tela é para lançar, não para ler item a item) -->
      <details class="itens-doc">
        <summary><strong>{{ a.itens.length }} material(is)</strong> · {{ totalUnidades(a) }} unidade(s)
          <span class="suave pequeno">— ver os materiais e lotes</span></summary>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Código AGHU</th><th>Material</th><th class="num">Qtd</th><th>Lote (qtd)</th></tr></thead>
        <tbody>
          <tr v-for="(i, n) in a.itens" :key="n" :class="{ 'sem-cod': !i.codigo_aghu }">
            <td class="mono">{{ i.codigo_aghu || 'sem código' }}</td>
            <td>{{ i.descricao }} <span v-if="i.consignado" class="etiqueta pequeno">consignado</span></td>
            <td class="num"><strong>{{ i.quantidade }}</strong></td>
            <td class="mono pequeno">
              <template v-if="i.lotes_qtd?.length"><span v-for="(l, k) in i.lotes_qtd" :key="k">{{ k ? ' · ' : '' }}{{ l.lote || 'sem lote' }} ({{ l.quantidade }})</span></template>
              <template v-else>{{ i.lotes.join(', ') }}</template></td>
          </tr>
        </tbody>
      </table></div>
      </details>
      <p v-if="a.sem_codigo" class="pequeno" style="color:var(--vermelho, #b3261e);margin:.4rem 0 0">
        {{ a.sem_codigo }} item(ns) sem código AGHU: o robô não lança — inclua à mão no AGHU.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const emit = defineEmits(['recarregar']);
const { f, postJson, baixar } = useTela();

// v18.7: o robô roda no computador de quem lança (o mesmo robô instalado da NF).
const chamando = ref('');
const msgRobo = ref('');
const erroRobo = ref(false);
const DOCS = [{ tipo: 'consumo', nome: 'Nota de consumo' }, { tipo: 'rm', nome: 'Requisição de material (RM)' }];

function totalUnidades(a: any) {
  return (a.itens || []).reduce((s: number, i: any) => s + (Number(i.quantidade) || 0), 0);
}
async function lancar(a: any, tipo: string) {
  if (a[tipo + '_status'] === 'em_lancamento' && !window.confirm('O robô já foi chamado para este paciente. Abrir de novo?')) return;
  chamando.value = a.id_atendimento + tipo;
  msgRobo.value = '';
  try {
    const r: any = await postJson(`/farmacia/nota-consumo/${a.id_atendimento}/aghu/lancar`, { servidor: window.location.origin, tipo });
    erroRobo.value = !r.ok;
    msgRobo.value = r.mensagem + (r.ok ? ' Se nada abrir em alguns segundos, o robô não está instalado neste computador (baixe o instalador acima).' : '');
    if (r.ok && r.link) window.location.href = r.link;
    setTimeout(() => emit('recarregar'), 1500);
  } catch {
    erroRobo.value = true;
    msgRobo.value = 'Falha de conexão com o TraceOPME. Tente de novo.';
  } finally {
    chamando.value = '';
  }
}
</script>

<style scoped>
.filtros-nc { display: flex; gap: 1rem; align-items: flex-end; flex-wrap: wrap; }
.filtros-nc .marcar { display: flex; gap: .4rem; align-items: center; margin-bottom: .5rem; }
.pac { border-left: 5px solid #8a94a3; }

.pac-topo { display: flex; gap: 1rem; align-items: flex-start; flex-wrap: wrap; margin-bottom: .5rem; }
.pac-id { flex: 1 1 280px; display: flex; flex-direction: column; gap: .1rem; }
.pac-id .nome { font-size: 1.08rem; }
.docs { display: flex; gap: .6rem; flex-wrap: wrap; }
.doc { border: 1px solid #e3e7ed; border-left: 4px solid #1f6fc4; border-radius: 10px; padding: .45rem .7rem; min-width: 250px;
  display: flex; flex-direction: column; gap: .25rem; }
.doc.st-lancada { border-left-color: #1e9e5a; } .doc.st-em_lancamento { border-left-color: #b7791f; }
.doc-cab { display: flex; gap: .5rem; align-items: center; justify-content: space-between; }
.doc-acoes { display: flex; gap: .6rem; align-items: center; }
.link-botao { background: none; border: 0; padding: 0; color: var(--azul, #0c3a67); text-decoration: underline; cursor: pointer; font-size: .85rem; }
.sem-cod td { color: #b3261e; }
.itens-doc > summary { cursor: pointer; padding: .35rem 0; }
.itens-doc[open] > summary { margin-bottom: .4rem; }
</style>
