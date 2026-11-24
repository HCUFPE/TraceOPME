<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Movimentações de dispensa</h1>
        <p>Tudo que saiu do almoxarifado para as farmácias e das farmácias para a sala, no período.
           Uma linha por unidade; a data é a do bip de saída.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/consultas">Voltar</a></div>
    </div>

    <form method="get" action="/consultas/dispensas" class="cartao">
      <div class="filtros">
        <div class="campo"><label>De</label><input type="date" name="inicio" :defaultValue="d.inicio"></div>
        <div class="campo"><label>Até</label><input type="date" name="fim" :defaultValue="d.fim"></div>
        <div class="campo"><label>Movimentação</label>
          <select name="tipo">
            <option v-for="(nome, k) in d.tipos" :key="k" :value="k" :selected="d.tipo === k">{{ nome }}</option>
          </select></div>
        <div class="campo"><label>Farmácia</label>
          <select name="farmacia">
            <option value="">todas</option>
            <option v-for="(nome, k) in d.farmacias" :key="k" :value="k" :selected="d.farmacia === k">{{ nome }}</option>
          </select></div>
        <div class="campo" style="flex:1"><label>Buscar</label>
          <input type="text" name="busca" :defaultValue="d.busca" placeholder="AGHU, descrição, lote, série ou prontuário"></div>
        <button class="botao">Filtrar</button>
      </div>
      <p class="pequeno suave" style="margin:.4rem 0 0">Farmácia: no envio do almoxarifado é a farmácia de destino;
        na dispensação para a sala é a farmácia que dispensou (Bloco Cirúrgico ou Hemodinâmica).</p>
    </form>

    <div class="grade grade-4" style="margin-bottom:1.25rem">
      <div class="cartao"><div class="rotulo">unidades movimentadas</div><div class="numero">{{ r.total }}</div></div>
      <div class="cartao"><div class="rotulo">almoxarifado → farmácia</div><div class="numero">{{ r.envios }}</div></div>
      <div class="cartao"><div class="rotulo">farmácia → sala</div><div class="numero">{{ r.dispensacoes }}</div></div>
      <div class="cartao"><div class="rotulo">retiradas antes de sair</div><div class="numero">{{ r.retirados }}</div></div>
    </div>

    <div v-if="r.por_aghu?.length" class="cartao" style="margin-bottom:1.25rem">
      <div class="entre"><h2>Por material (código AGHU)</h2>
        <span class="pequeno suave"><template v-for="(p, n) in r.por_fluxo" :key="n">{{ p[0] }}: <strong>{{ p[1] }}</strong><template v-if="n < r.por_fluxo.length - 1"> · </template></template></span></div>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>AGHU</th><th>Descrição AGHU</th><th class="num">Almoxarifado → Farmácia</th><th class="num">Farmácia → Sala</th></tr></thead>
          <tbody>
            <tr v-for="(x, n) in r.por_aghu" :key="n"><td class="mono">{{ x.codigo_aghu }}</td><td>{{ x.descricao }}</td>
                <td class="num">{{ x.envios }}</td><td class="num">{{ x.dispensacoes }}</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="cartao">
      <div class="entre">
        <h2>{{ d.linhas.length }} movimentação(ões)</h2>
        <div v-if="d.linhas.length" class="linha-botoes">
          <a class="botao secundario" data-baixar :href="url('csv')">Exportar planilha (CSV)</a>
          <a class="botao" data-baixar :href="url('pdf')">Baixar PDF</a>
        </div>
      </div>
      <div v-if="d.linhas.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Data</th><th>Movimentação</th><th>Documento</th><th>Material (descrição AGHU)</th><th>Lote</th>
                     <th>Validade</th><th>Nº série</th><th>Paciente</th><th>Por</th><th>Situação</th></tr></thead>
          <tbody>
            <tr v-for="(l, n) in d.linhas" :key="n" :style="!l.conta ? 'opacity:.6' : ''">
              <td class="pequeno">{{ f.dataHoraBr(l.data) }}</td>
              <td class="pequeno"><strong>{{ l.origem }}</strong> → {{ l.destino }}</td>
              <td class="mono pequeno">{{ l.documento }}</td>
              <td>{{ l.descricao }}<br><span class="mono pequeno suave">AGHU {{ l.codigo_aghu || '—' }}</span></td>
              <td class="mono">{{ l.lote || '—' }}</td>
              <td>{{ f.dataBr(l.validade) || '—' }}</td>
              <td class="mono pequeno">{{ l.serie || '—' }}</td>
              <td class="pequeno"><template v-if="l.prontuario">{{ l.prontuario }} · {{ l.paciente }}<br>
                  <span class="suave">{{ l.unidade }}<template v-if="l.especialidade"> · {{ l.especialidade }}</template></span></template><template v-else>—</template></td>
              <td class="pequeno">{{ l.por || '—' }}</td>
              <td class="pequeno">{{ l.situacao }}<template v-if="l.recebido_por"><br><span class="suave">por {{ l.recebido_por }}</span></template>
                  <br><span class="suave">hoje: {{ l.situacao_atual }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhuma movimentação de dispensa no período.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const r = computed(() => props.d.resumo || {});
function url(formato: string) {
  const p = new URLSearchParams({
    inicio: props.d.inicio || '', fim: props.d.fim || '', tipo: props.d.tipo || '',
    farmacia: props.d.farmacia || '', busca: props.d.busca || '', exportar: formato,
  });
  return `/consultas/dispensas?${p.toString()}`;
}
</script>
