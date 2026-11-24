<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Material não cadastrado usado na sala</h1>
        <p>Exceção: a sala usou material que não existia no sistema e registrou lote e validade
           (a etiqueta foi colada no formulário de rastreabilidade ou fotografada). Complete o cadastro para fechar o rastro:
           descrição, AGHU, NF e tipo de entrada.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/almoxarifado">Voltar</a></div>
    </div>

    <div class="cartao">
      <h2>Aguardando regularização ({{ d.pendentes.length }})</h2>
      <form v-for="r in d.pendentes" :key="r.id" method="post" :action="`/almoxarifado/nao-cadastrados/${r.id}/regularizar`"
            style="border-top:1px solid var(--borda);padding:.9rem 0">
        <p style="margin:0 0 .4rem"><strong>{{ r.xProd }}</strong> · lote <span class="mono">{{ r.nLote }}</span>
          · val. {{ f.dataBr(r.dVal) }} · {{ r.fornecedor }}<template v-if="r.marca_fabricante"> / {{ r.marca_fabricante }}</template>
          <br><span class="pequeno suave">Prontuário <strong>{{ r.prontuario }}</strong><template v-if="r.paciente"> · {{ r.paciente }}</template>
          · {{ f.rotuloUnidade(r.unidade) }} sala {{ r.sala }} · registrado em {{ f.dataHoraBr(r.registrado_em) }} por {{ r.registrado_por }}<template v-if="r.autorizado_por && r.autorizado_por !== r.registrado_por">,
          autorizado por {{ r.autorizado_por }}</template> · motivo: {{ r.motivo }}<template v-if="r.detalhe"> ({{ r.detalhe }})</template></span>
          <template v-if="r.foto"><br><a class="pequeno" href="#" @click.prevent="fotoAberta = fotoAberta === r.id ? null : r.id">ver foto da etiqueta</a>
            <ImagemApi v-if="fotoAberta === r.id" :src="`/sala-procedimento/nao-cadastrado/foto/${r.foto}`" alt="foto"
                       style="display:block;max-width:420px;margin-top:.4rem;border:1px solid var(--borda);border-radius:6px" /></template></p>
        <div class="grade grade-3">
          <div class="campo" style="grid-column:span 2"><label :class="{ obrigatorio: semId(r) }">Descrição do material</label>
            <input type="text" name="xProd" :required="semId(r)" :defaultValue="semId(r) ? '' : r.xProd"
                   :placeholder="semId(r) ? 'a sala não identificou — veja a etiqueta ou a foto' : ''"></div>
          <div class="campo"><label>Fornecedor</label>
            <input type="text" name="fornecedor" :defaultValue="r.fornecedor === 'NÃO INFORMADO' ? '' : r.fornecedor"></div>
          <div class="campo"><label>Fabricante / marca</label>
            <input type="text" name="marca_fabricante" :defaultValue="r.marca_fabricante || ''"></div>
          <div class="campo"><label class="obrigatorio">Código AGHU</label>
            <input type="text" name="codigo_aghu" required :defaultValue="r.codigo_aghu || ''"></div>
          <div class="campo"><label>Código de barras</label>
            <input type="text" name="codigo_barras" :defaultValue="r.codigo_barras || ''"></div>
          <div class="campo"><label>Nº da NF</label>
            <input type="text" name="numero_nf" :defaultValue="r.numero_nf || ''"></div>
          <div class="campo"><label>Tipo de entrada</label>
            <select name="tipo_entrada">
              <option v-for="(rotulo, chave) in d.tipos" :key="chave" :value="chave" :selected="chave === (r.tipo_entrada || 'consignado')">{{ rotulo }}</option>
            </select></div>
          <div class="campo"><label>Valor unitário</label>
            <input type="text" name="vUnCom" :defaultValue="r.vUnCom || ''" placeholder="0,00"></div>
          <div class="campo"><label>Observação</label>
            <input type="text" name="observacao" placeholder="ex.: NF chegou depois"></div>
        </div>
        <button class="botao">Regularizar</button>
      </form>
      <p v-if="!d.pendentes.length" class="vazio">Nada aguardando regularização.</p>
    </div>

    <div v-if="d.regularizados?.length" class="cartao">
      <h2>Regularizados recentemente</h2>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Material</th><th>AGHU</th><th>Lote</th><th>Prontuário</th><th>Regularizado</th></tr></thead>
        <tbody>
          <tr v-for="r in d.regularizados" :key="r.id"><td>{{ r.xProd }}</td><td class="mono pequeno">{{ r.codigo_aghu }}</td><td class="mono">{{ r.nLote }}</td>
            <td>{{ r.prontuario }}</td><td class="pequeno">{{ f.dataHoraBr(r.regularizado_em) }} · {{ r.regularizado_por }}</td></tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import ImagemApi from '../../components/opme/ImagemApi.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
const fotoAberta = ref<number | null>(null);
const semId = (r: any) => r.xProd === 'MATERIAL NÃO IDENTIFICADO (ver etiqueta)';
</script>
