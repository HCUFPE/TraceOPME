<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Vincular uso a empenho</h1>
        <p>Materiais consignados já utilizados no paciente, aguardando vínculo ao empenho do
           fornecedor antes de solicitar a nota fiscal.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/consignados">Voltar</a></div>
    </div>

    <template v-if="d.itens?.length">
      <div v-for="item in d.itens" :key="item.id_unidade" class="cartao">
        <div class="entre">
          <div>
            <strong>{{ item.xProd }}</strong>
            <span class="suave pequeno mono"> <template v-if="item.codigo_consignado">consignado {{ item.codigo_consignado }} · </template>AGHU {{ item.codigo_aghu || '—' }} · lote {{ item.nLote || '—' }}
              <template v-if="item.numero_serie"> · série {{ item.numero_serie }}</template></span><br>
            <span class="pequeno">Fornecedor: {{ item.fornecedor || '—' }} ·
              Prontuário {{ item.prontuario || '—' }} ({{ item.paciente || 'sem nome' }}) ·
              Sala {{ item.sala || '—' }}</span>
          </div>
          <span class="suave pequeno">{{ item.data_uso ? f.dataHoraBr(item.data_uso) : '' }}</span>
        </div>

        <form v-if="item.candidatos?.length" method="post" action="/consignados/vincular" style="margin-top:.75rem">
          <input type="hidden" name="id_unidade" :value="item.id_unidade">
          <div class="grade grade-2">
            <div class="campo">
              <label class="obrigatorio">Empenho</label>
              <select name="id_empenho" required>
                <option value="">selecione</option>
                <option v-for="e in item.candidatos" :key="e.id_empenho" :value="e.id_empenho">
                  {{ e.identificacao || e.numero }} — {{ e.material }} ({{ e.saldo }} de {{ e.quantidade_total }} restantes)
                </option>
              </select>
            </div>
            <div class="campo">
              <label>Observação <span class="opcional">(opcional)</span></label>
              <input type="text" name="observacao">
            </div>
          </div>
          <button class="botao pequeno">Vincular</button>
        </form>
        <div v-else class="aviso alerta" style="margin-top:.75rem">
          Nenhum empenho ativo com saldo para {{ item.fornecedor || 'este fornecedor' }}.
          <a href="/consignados/empenhos/novo">Cadastrar empenho</a> ou solicitar mais saldo
          à gestão antes de vincular este uso.
        </div>
      </div>
    </template>
    <div v-else class="cartao"><p class="vazio">Nenhum consignado utilizado aguardando vínculo. Tudo em dia.</p></div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
