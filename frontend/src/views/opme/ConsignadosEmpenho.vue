<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Empenho {{ e.identificacao }}</h1>
        <p>{{ e.fornecedor }} · {{ e.material }} · <CodigosEmpenho :e="e" /></p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/consignados/empenhos">Voltar</a></div>
    </div>

    <div v-if="e.no_limite" class="aviso erro" style="margin-bottom:1rem">
      <strong>{{ e.saldo === 0 ? 'Empenho SEM SALDO.' : 'Limite de segurança atingido.' }}</strong>
      Restam {{ e.saldo }} de {{ e.quantidade_total }} unidade(s) (limite: {{ e.limite }}).
      Providencie novo empenho{{ e.saldo === 0 ? '' : ' antes que o saldo acabe' }}.
    </div>

    <div class="grade grade-4" style="margin-bottom:1.5rem">
      <div class="cartao"><div class="numero">{{ e.quantidade_total }}</div><div class="rotulo">unidades no empenho</div></div>
      <div class="cartao"><div class="numero">{{ e.utilizados }}</div><div class="rotulo">vinculadas / utilizadas</div></div>
      <div class="cartao"><div class="numero">{{ e.saldo }}</div><div class="rotulo">saldo disponível</div></div>
      <div class="cartao"><div class="numero">{{ f.moeda(e.valor_saldo) }}</div><div class="rotulo">valor do saldo</div></div>
    </div>

    <div class="cartao">
      <h2>Dados do empenho</h2>
      <div class="grade grade-2">
        <p><strong>Número do empenho:</strong> {{ e.numero || '—' }}</p>
        <p><strong>Data:</strong> {{ f.dataBr(e.data_empenho) || '—' }}</p>
        <p><strong>Vigência:</strong> {{ f.dataBr(e.vigencia_inicio) || '—' }} a {{ f.dataBr(e.vigencia_fim) || '—' }}
          <span v-if="e.vigencia === 'vencida'" class="etiqueta vermelho">vencida — não recebe débito</span>
          <span v-else-if="e.vigencia === 'futura'" class="etiqueta cinza">ainda não vigente</span></p>
        <p><strong>Nº do processo:</strong> {{ e.numero_processo || '—' }}</p>
        <p><strong>Nº do pregão:</strong> {{ e.numero_pregao || '—' }}</p>
        <p><strong>Nº do registro de licitação:</strong> {{ e.numero_registro || '—' }}</p>
        <p><strong>Quantidade licitada:</strong> {{ e.quantidade_total }} unidade(s)</p>
        <p><strong>Valor unitário:</strong> {{ f.moeda(e.valor_unitario) }}</p>
        <p><strong>Valor total:</strong> {{ f.moeda(e.valor_total) }}</p>
        <p><strong>Limite de segurança:</strong> {{ e.limite }} unidade(s)</p>
        <p><strong>Débito automático:</strong>
          <template v-if="e.pares?.length">cada uso de unidade com o código consignado
            {{ e.codigos_consignado.join(', ') }}</template>
          <template v-else>cada uso de AGHU {{ aghu || '—' }}</template></p>
        <div v-if="e.pares?.length" style="grid-column:1 / -1">
          <strong>Códigos cobertos:</strong>
          <table style="margin-top:.3rem;max-width:36rem"><thead><tr><th>Código consignado</th><th>Código AGHU</th></tr></thead>
            <tbody><tr v-for="p in e.pares" :key="p.consignado"><td class="mono">{{ p.consignado }}</td><td class="mono">{{ p.aghu || '—' }}</td></tr></tbody></table>
        </div>
        <p><strong>Situação:</strong>
          <span :class="['etiqueta', e.status === 'ativo' ? 'verde' : 'cinza']">{{ titulo(e.status) }}</span>
        </p>
      </div>
      <p v-if="e.observacao" class="suave pequeno">{{ e.observacao }}</p>

      <form v-if="e.status === 'ativo'" method="post" :action="`/consignados/empenhos/${e.id_empenho}/encerrar`"
            data-confirmar="Encerrar este empenho? Ele deixa de aparecer como opção para novos vínculos.">
        <div class="campo" style="max-width:420px">
          <label>Motivo do encerramento <span class="opcional">(opcional)</span></label>
          <input type="text" name="motivo" placeholder="Ex.: empenho vencido, saldo zerado e não renovado">
        </div>
        <button class="botao secundario pequeno">Encerrar empenho</button>
      </form>
    </div>

    <div class="cartao">
      <div class="entre" style="flex-wrap:wrap;gap:.8rem;align-items:flex-end">
        <h2 style="margin:0">Materiais vinculados</h2>
        <form method="get" :action="`/consignados/empenhos/${e.id_empenho}`"
              style="display:flex;gap:.5rem;align-items:flex-end;flex-wrap:wrap">
          <div class="campo" style="margin:0"><label class="pequeno">De</label>
            <input type="date" name="inicio" :defaultValue="d.inicio"></div>
          <div class="campo" style="margin:0"><label class="pequeno">Até</label>
            <input type="date" name="fim" :defaultValue="d.fim"></div>
          <button class="botao secundario">Filtrar</button>
          <a v-if="d.inicio || d.fim" class="botao secundario" :href="`/consignados/empenhos/${e.id_empenho}`">Limpar</a>
          <a class="botao" data-baixar :href="`/consignados/empenhos/${e.id_empenho}/pdf?inicio=${d.inicio || ''}&fim=${d.fim || ''}`">Baixar PDF</a>
        </form>
      </div>
      <p class="pequeno suave" style="margin:.4rem 0 .8rem">
        {{ d.vinculos.length }} material(is) vinculado(s)<template v-if="d.inicio || d.fim"> de {{ f.dataBr(d.inicio) || 'início' }} a {{ f.dataBr(d.fim) || 'hoje' }}</template>.
        A data é a do uso no paciente (débito no empenho).</p>
      <div v-if="d.vinculos.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Produto (descrição AGHU)</th><th>Lote</th><th>Validade</th><th>Nº série</th><th>Prontuário</th><th>Paciente</th>
                     <th>Especialidade</th><th>Unidade</th><th>Quando</th><th></th></tr></thead>
          <tbody>
            <tr v-for="v in d.vinculos" :key="v.id_vinculo">
              <td>{{ v.descricao_aghu }}<br><span class="suave pequeno mono">AGHU {{ v.codigo_aghu || '—' }}<template v-if="v.codigo_consignado"> · consignado {{ v.codigo_consignado }}</template></span></td>
              <td class="mono">{{ v.nLote || '—' }}</td>
              <td>{{ f.dataBr(v.dVal) || '—' }}</td>
              <td class="mono">{{ v.numero_serie || '—' }}</td>
              <td>{{ v.prontuario || '—' }}</td>
              <td>{{ v.paciente || '—' }}<template v-if="v.sala"><br><span class="suave pequeno">sala {{ v.sala }}</span></template></td>
              <td class="pequeno">{{ v.especialidade || '—' }}</td>
              <td class="pequeno">{{ v.unidade_rotulo }}</td>
              <td class="pequeno">{{ f.dataHoraBr(v.data_vinculo) }}</td>
              <td>
                <form v-if="v.status === 'ativo'" method="post" :action="`/consignados/vinculo/${v.id_vinculo}/cancelar`"
                      data-confirmar="Cancelar este vínculo? O saldo do empenho volta."
                      style="display:flex;gap:.3rem">
                  <input type="text" name="motivo" placeholder="motivo" required style="width:140px">
                  <button class="botao pequeno secundario">Cancelar</button>
                </form>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">{{ d.inicio || d.fim ? 'Nenhum material vinculado neste período.' : 'Nenhum material vinculado a este empenho ainda.' }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import CodigosEmpenho from '../../components/opme/CodigosEmpenho.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const e = computed(() => props.d.empenho);
const aghu = computed(() => (e.value.codigos_aghu || []).join(', '));
const titulo = (s: string) => String(s || '').toLowerCase().replace(/(^|\s)\S/g, (c) => c.toUpperCase());
</script>
