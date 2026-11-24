<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Histórico de movimentações</h1>
        <p>Todo movimento fica registrado — nada é apagado ou reescrito. Filtre por período, local,
           prontuário e tipo; exporte para planilha.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/consultas">Voltar</a></div>
    </div>

    <form method="get" action="/consultas/eventos" class="cartao">
      <div class="filtros">
        <div class="campo"><label>De</label><input type="date" name="inicio" :defaultValue="d.inicio"></div>
        <div class="campo"><label>Até</label><input type="date" name="fim" :defaultValue="d.fim"></div>
        <div class="campo">
          <label>Unidade</label>
          <select name="unidade">
            <option value="">todas</option>
            <option v-for="(dados, chave) in d.unidades" :key="chave" :value="chave" :selected="d.unidade === chave">{{ dados.rotulo }}</option>
          </select>
        </div>
        <div class="campo"><label>Sala</label>
          <input type="text" name="sala" :defaultValue="d.sala" placeholder="ex.: 03" style="width:90px"></div>
        <div class="campo"><label>Prontuário ou paciente</label>
          <input type="text" name="prontuario" :defaultValue="d.prontuario"></div>
        <div class="campo">
          <label>Movimento</label>
          <select name="tipo">
            <option value="">todos</option>
            <option v-for="(dados, chave) in d.tipos" :key="chave" :value="chave" :selected="d.tipo === chave">{{ dados[0] }}</option>
          </select>
        </div>
        <div class="campo"><label>Usuário</label>
          <input type="text" name="usuario" :defaultValue="d.usuario_filtro" style="width:130px"></div>
        <button class="botao">Filtrar</button>
      </div>
      <p class="suave pequeno" style="margin:.6rem 0 0">
        O período é a data do movimento. Sem filtro, mostra os últimos 30 dias.
        Sala e prontuário valem para movimentos ligados a um atendimento (uso, devolução, exclusão, estorno).
      </p>
    </form>

    <div class="cartao">
      <div class="entre" style="flex-wrap:wrap;gap:.6rem">
        <h2 style="margin:0">{{ d.total }} movimento(s)<template v-if="d.total > d.eventos.length"> — mostrando os {{ d.eventos.length }} mais recentes</template></h2>
        <a v-if="d.total" class="botao secundario pequeno" data-baixar :href="`/consultas/eventos?${d.query ? d.query + '&' : ''}formato=csv`">Exportar planilha (CSV)</a>
      </div>
      <div class="tabela-rolagem" style="margin-top:.8rem">
        <table>
          <thead><tr><th>Quando</th><th>Movimento</th><th>Local</th><th>Prontuário</th><th>Material</th>
                     <th>Usuário (login)</th><th>Devolvido por</th><th>Recebido por</th><th>Motivo / observação</th></tr></thead>
          <tbody>
            <tr v-for="e in d.eventos" :key="e.id_evento">
              <td class="pequeno" style="white-space:nowrap">{{ f.dataHoraBr(e.data_evento) }}</td>
              <td><span :class="['etiqueta', cor(e.tipo)]">{{ e.movimento }}</span></td>
              <td class="pequeno"><template v-if="e.sala">{{ e.rotulo_unidade }} — sala {{ e.sala }}</template><template v-else>—</template></td>
              <td class="pequeno">
                <template v-if="e.prontuario">
                  <a :href="`/sala-procedimento/atendimento/${e.id_atendimento}`">{{ e.prontuario }}</a>
                  <template v-if="e.paciente"><br><span class="suave">{{ e.paciente }}</span></template>
                </template><template v-else>—</template>
              </td>
              <td class="pequeno">
                <template v-if="CAIXA.includes(e.tipo) && e.caixa">
                  <strong>Caixa <span class="mono">{{ e.caixa }}</span></strong>
                  <template v-if="e.tipo === 'devolver_caixa'"> — {{ (e.itens_caixa || []).length }} item(ns)</template><br>
                  <a :href="`/consultas/caixa/${e.caixa}?evento=${e.id_evento}`">ver a caixa neste momento</a>
                  <details v-if="e.itens_caixa?.length" style="margin-top:.3rem">
                    <summary style="cursor:pointer" class="suave">itens devolvidos</summary>
                    <div v-for="(i, n) in e.itens_caixa" :key="n" class="mono">{{ i.codigo_aghu || '—' }} · {{ i.descritivo_hospital || i.xProd }} · lote {{ i.nLote || '—' }}</div>
                  </details>
                </template>
                <template v-else-if="e.id_unidade">
                  <a :href="`/consultas/item/${e.id_unidade}`">{{ e.descritivo_hospital || e.xProd || e.id_unidade }}</a><br>
                  <span class="suave mono">AGHU {{ e.codigo_aghu || '—' }} · lote {{ e.nLote || '—' }}</span>
                  <template v-if="e.caixa"><br><a class="suave" :href="`/consultas/caixa/${e.caixa}?evento=${e.id_evento}`">caixa {{ e.caixa }}</a></template>
                </template>
                <template v-else>—</template>
              </td>
              <td class="pequeno">{{ e.usuario || '—' }}</td>
              <td class="pequeno"><span v-if="e.devolvido_por" class="etiqueta azul">{{ e.devolvido_por }}</span><template v-else>—</template></td>
              <td class="pequeno"><span v-if="e.recebido_por" class="etiqueta verde">{{ e.recebido_por }}</span><template v-else>—</template></td>
              <td class="pequeno">{{ e.motivo || '' }} <span class="suave">{{ e.observacao || '' }}</span></td>
            </tr>
            <tr v-if="!d.eventos.length"><td colspan="9" class="vazio">Nenhum movimento com esses filtros.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
const CAIXA = ['devolver_caixa', 'devolucao_caixa_divergente', 'conferir_caixa'];
const VERMELHOS = ['excluir_bip', 'estornar_uso', 'desfazer', 'atendimento_cancelado', 'baixar', 'marcar_divergencia', 'devolucao_caixa_divergente'];
function cor(tipo: string) {
  if (tipo === 'registrar_uso') return 'verde';
  if (tipo === 'devolver_nao_utilizado' || tipo === 'devolver_caixa') return 'azul';
  if (VERMELHOS.includes(tipo)) return 'vermelho';
  return 'cinza';
}
</script>
