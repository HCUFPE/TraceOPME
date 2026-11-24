<template>
  <div>
    <!-- Correção de uma unidade por vez. -->
    <details v-for="item in itens" :key="item.id_unidade" class="cartao">
      <summary style="cursor:pointer">
        <strong>{{ item.xProd }}</strong>
        <span class="suave pequeno"> · lote {{ item.nLote || '—' }} · val. {{ f.dataBr(item.dVal) || '—' }} </span>
        <span :class="['etiqueta', f.corStatus(item.status)]">{{ f.rotuloStatus(item.status) }}</span>
        <span class="mono pequeno suave"> {{ item.id_unidade }}</span>
      </summary>

      <form method="post" :action="`/almoxarifado/correcoes/${item.id_unidade}`" style="margin-top:1rem">
        <input type="hidden" name="busca" :value="busca">
        <div class="grade grade-3">
          <div class="campo"><label>Descrição</label><input type="text" name="xProd" :defaultValue="item.xProd"></div>
          <div class="campo"><label>Código de barras</label><input type="text" name="codigo_barras" :defaultValue="item.codigo_barras"></div>
          <div class="campo"><label>Código AGHU</label><input type="text" name="codigo_aghu" :defaultValue="item.codigo_aghu || ''"></div>
          <div class="campo"><label>Marca/Fabricante</label><input type="text" name="marca_fabricante" :defaultValue="item.marca_fabricante || ''"></div>
          <div class="campo"><label>Fornecedor</label><input type="text" name="fornecedor" :defaultValue="item.fornecedor || ''"></div>
          <div class="campo"><label>Lote</label><input type="text" name="nLote" :defaultValue="item.nLote || ''"></div>
          <div class="campo"><label>Nº de série</label><input type="text" name="numero_serie" :defaultValue="item.numero_serie || ''"></div>
          <div class="campo"><label>Fabricação</label><input type="date" name="dFab" :defaultValue="item.dFab || ''"></div>
          <div class="campo"><label>Validade</label><input type="date" name="dVal" :defaultValue="item.dVal || ''"></div>
          <div class="campo"><label>Valor unitário</label><input type="text" name="vUnCom" :defaultValue="item.vUnCom || 0"></div>
          <div class="campo">
            <label>Classificação</label>
            <select name="tipo_entrada" v-model="tipos_sel[item.id_unidade]">
              <option v-for="(nome, codigo) in tipos" :key="codigo" :value="codigo">{{ nome }}</option>
            </select>
          </div>
          <div v-if="tipos_sel[item.id_unidade] === 'consignado' || item.codigo_consignado" class="campo">
            <label :class="{ obrigatorio: tipos_sel[item.id_unidade] === 'consignado' }">Código consignado</label>
            <input type="text" name="codigo_consignado" :defaultValue="item.codigo_consignado || ''" :required="tipos_sel[item.id_unidade] === 'consignado'">
          </div>
        </div>
        <div class="campo">
          <label class="obrigatorio">Motivo da correção</label>
          <input type="text" name="motivo" required placeholder="Ex.: validade digitada errada na entrada">
        </div>
        <div class="linha-botoes">
          <button class="botao">Salvar correção</button>
          <a class="botao secundario" :href="`/consultas/item/${item.id_unidade}`">Ver histórico</a>
        </div>
      </form>

      <!-- nov/2026: excluir o item cadastrado por engano / ajustar a quantidade. -->
      <div class="grade grade-2" style="margin-top:1rem;border-top:1px solid var(--borda);padding-top:.8rem;align-items:start">
        <form v-if="!idsEmGrupo?.includes(item.id_unidade)" method="post" action="/almoxarifado/correcoes/quantidade"
              data-confirmar="Ajustar a quantidade deste cadastro?">
          <input type="hidden" name="busca" :value="busca">
          <input type="hidden" name="ids" :value="item.id_unidade">
          <div class="campo">
            <label class="obrigatorio">Quantidade correta <span class="opcional">(hoje: 1 unidade)</span></label>
            <input type="number" name="quantidade" min="0" max="500" required inputmode="numeric">
            <div class="dica">Cadastrou 1 e eram mais? Informe o total — as que faltam entram com os mesmos dados
              (só cadastro manual). 0 exclui este item.</div>
          </div>
          <div class="campo"><label class="obrigatorio">Motivo</label>
            <input type="text" name="motivo" required minlength="5" placeholder="Ex.: eram 3 unidades"></div>
          <button class="botao secundario">Ajustar quantidade</button>
        </form>
        <p v-else class="pequeno suave" style="margin:0">Este item faz parte de um cadastro de várias unidades: para corrigir
          a quantidade, use o quadro “Corrigir N unidades de uma vez”, acima.</p>
        <form method="post" action="/almoxarifado/correcoes/excluir"
              data-confirmar="Excluir este item do estoque? O registro continua no histórico, com o motivo.">
          <input type="hidden" name="busca" :value="busca">
          <input type="hidden" name="ids" :value="item.id_unidade">
          <div class="campo"><label class="obrigatorio">Cadastrado por engano? Motivo da exclusão</label>
            <input type="text" name="motivo" required minlength="5" placeholder="Ex.: cadastrado no produto errado"></div>
          <button class="botao perigo">Excluir este item</button>
          <div class="dica">Só sai o que ainda está parado no almoxarifado, sem nenhuma movimentação.</div>
        </form>
      </div>
    </details>
    <div v-if="!itens?.length" class="cartao"><p class="vazio">Nenhum item encontrado para “{{ busca }}”.</p></div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue';
import { useFormatos } from '../../utils/formatos';

const props = defineProps<{ itens: any[]; busca: string; tipos: Record<string, string>; idsEmGrupo?: string[] }>();
const f = useFormatos();
// Classificação escolhida em cada item: "Consignado" abre o campo do código consignado.
const tipos_sel = reactive<Record<string, string>>({});
watch(() => props.itens, (lista) => (lista || []).forEach((i: any) => {
  if (!(i.id_unidade in tipos_sel)) tipos_sel[i.id_unidade] = i.tipo_entrada || 'aquisicao_propria';
}), { immediate: true });
</script>
