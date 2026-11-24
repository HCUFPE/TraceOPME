<template>
  <!-- v18.4.7: o código consignado não é digitado. Ele vem da relação
       AGHU × código consignado (Consignados → Código consignado × AGHU), pelo AGHU do material. -->
  <div class="campo-consignado">
    <template v-if="!String(aghu || '').trim()">
      <div class="dica">Preencha o código AGHU: o código consignado vem da relação com ele.</div>
    </template>
    <template v-else-if="carregando"><div class="dica">Buscando o código consignado do AGHU {{ aghu }}…</div></template>
    <template v-else-if="opcoes.length === 1">
      <input type="hidden" name="codigo_consignado" :value="opcoes[0].codigo_consignado">
      <div class="dica">✔ Código consignado <strong class="mono">{{ opcoes[0].codigo_consignado }}</strong>
        <template v-if="opcoes[0].fornecedor"> · {{ opcoes[0].fornecedor }}</template> (pela relação com o AGHU)</div>
    </template>
    <template v-else-if="opcoes.length > 1">
      <select name="codigo_consignado" required>
        <option v-for="o in opcoes" :key="o.codigo_consignado" :value="o.codigo_consignado"
                :selected="o.codigo_consignado === inicial">{{ o.codigo_consignado }}{{ o.fornecedor ? ' · ' + o.fornecedor : '' }}</option>
      </select>
      <div class="dica">O AGHU {{ aghu }} tem mais de um código consignado. Escolha o deste material.</div>
    </template>
    <div v-else class="dica" style="color:#8a5a00">
      O AGHU {{ aghu }} ainda não tem código consignado na relação: por enquanto o código consignado
      será o próprio AGHU ({{ aghu }}). Dá para corrigir depois em
      <a href="/consignados/associacoes">Consignados → Código consignado × AGHU</a>.</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { getJson } from '../../services/opme';

const props = withDefaults(defineProps<{ aghu: string; inicial?: string; base?: string }>(),
  { inicial: '', base: '/almoxarifado' });
const opcoes = ref<any[]>([]);
const carregando = ref(false);
let espera: ReturnType<typeof setTimeout> | undefined;

async function consultar() {
  const a = String(props.aghu || '').trim();
  opcoes.value = [];
  if (!a) return;
  carregando.value = true;
  try {
    const dd: any = await getJson(`${props.base}/consignado-aghu`, { aghu: a });
    if (String(props.aghu || '').trim() === a) opcoes.value = dd.opcoes || [];
  } catch {
    opcoes.value = [];
  } finally {
    carregando.value = false;
  }
}

watch(() => props.aghu, () => { clearTimeout(espera); espera = setTimeout(consultar, 350); }, { immediate: true });
</script>
