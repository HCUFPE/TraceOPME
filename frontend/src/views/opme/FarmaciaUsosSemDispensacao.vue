<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Usos sem dispensação — ciência da farmácia</h1>
        <p>Material que a sala usou no paciente sem ter sido dispensado pela farmácia. A saída já foi
           registrada no uso; a farmácia precisa <strong>dar ciência</strong> de cada caso. Entra no indicador “Ciência da farmácia em até 24 h”.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />

    <form method="post" action="/farmacia/usos-sem-dispensacao/ciencia" class="cartao"
          :style="`border-left:5px solid ${d.pendentes.length ? 'var(--vermelho, #b3261e)' : 'var(--verde, #14a38b)'}`">
      <h2>Aguardando ciência ({{ d.pendentes.length }})</h2>
      <template v-if="d.pendentes.length">
        <div class="tabela-rolagem"><table>
          <thead><tr><th><input type="checkbox" style="width:auto" title="marcar todos" :checked="marcados.length === d.pendentes.length" @change="marcarTodos"></th>
                     <th>Usado em</th><th>Material</th><th>AGHU</th><th>Lote</th><th>Prontuário</th><th>Local</th><th>Quem usou</th></tr></thead>
          <tbody>
            <tr v-for="u in d.pendentes" :key="u.id">
              <td><input type="checkbox" name="ids" :value="String(u.id)" v-model="marcados" style="width:1.3rem;height:1.3rem"></td>
              <td class="pequeno">{{ f.dataHoraBr(u.usado_em) }}</td>
              <td>{{ u.descritivo_hospital || u.xProd }}<template v-if="u.tipo_entrada === 'consignado'"> <span class="etiqueta azul">consignado</span></template></td>
              <td class="mono pequeno">{{ u.codigo_aghu || '—' }}</td>
              <td class="mono">{{ u.nLote || '—' }}</td>
              <td><strong>{{ u.prontuario || '—' }}</strong><template v-if="u.paciente"><br><span class="suave pequeno">{{ u.paciente }}</span></template></td>
              <td class="pequeno">{{ f.rotuloUnidade(u.unidade) }} — sala {{ u.sala }}</td>
              <td class="pequeno">{{ u.usado_por }}</td>
            </tr>
          </tbody>
        </table></div>
        <div style="display:flex;gap:.6rem;align-items:flex-end;flex-wrap:wrap;margin-top:.8rem">
          <div class="campo" style="margin:0;flex:1 1 20rem"><label>Observação <span class="opcional">(opcional — ex.: urgência, reposto no kit)</span></label>
            <input type="text" name="observacao"></div>
          <button class="botao">Dar ciência dos marcados</button>
        </div>
      </template>
      <p v-else class="vazio">Nenhum uso sem dispensação aguardando ciência.</p>
    </form>

    <div v-if="d.cientes?.length" class="cartao">
      <h2>Ciências recentes</h2>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Usado em</th><th>Material</th><th>Prontuário</th><th>Ciência em</th><th>Quem deu ciência</th><th>Observação</th></tr></thead>
        <tbody>
          <tr v-for="u in d.cientes" :key="u.id">
            <td class="pequeno">{{ f.dataHoraBr(u.usado_em) }}</td>
            <td class="pequeno">{{ u.descritivo_hospital || u.xProd }} <span class="mono suave">lote {{ u.nLote || '—' }}</span></td>
            <td class="pequeno">{{ u.prontuario || '—' }}</td>
            <td class="pequeno">{{ f.dataHoraBr(u.ciente_em) }}</td>
            <td><span class="etiqueta verde">{{ u.ciente_nome }}</span></td>
            <td class="pequeno">{{ u.observacao || '' }}</td>
          </tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const marcados = ref<string[]>([]);
function marcarTodos(e: Event) {
  marcados.value = (e.target as HTMLInputElement).checked ? props.d.pendentes.map((u: any) => String(u.id)) : [];
}
</script>
