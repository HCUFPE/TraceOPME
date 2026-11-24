<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Devolução {{ dv.id_devolucao }}</h1>
        <p>{{ dv.fornecedor }} · criada em {{ f.dataHoraBr(dv.criada_em) }} por {{ dv.criada_por }}
          <span :class="['etiqueta', dv.status === 'finalizada' ? 'verde' : dv.status === 'aberta' ? 'amarelo' : 'vermelho']">{{ dv.rotulo_status }}</span></p>
      </div>
      <div class="acoes">
        <a v-if="dv.qtd_itens" class="botao" data-baixar :href="`/almoxarifado/devolucao-fornecedor/${dv.id_devolucao}/pdf`">Baixar romaneio (PDF)</a>
        <a class="botao secundario" href="/almoxarifado/romaneios-fornecedor">Voltar</a>
      </div>
    </div>

    <div v-if="dv.status === 'cancelada'" class="aviso erro">
      Cancelada em {{ f.dataHoraBr(dv.cancelada_em) }} por {{ dv.cancelada_por }} — {{ dv.motivo_cancelamento }}.
      Os itens voltaram ao estoque.
    </div>
    <div v-else-if="dv.status === 'aberta'" class="aviso info" style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap">
      <span style="flex:1 1 300px">Aberta: os itens que você bipar em “Devolver ao fornecedor” para <strong>{{ dv.fornecedor }}</strong>
        entram aqui. Quando terminar, finalize e baixe o romaneio.</span>
      <a class="botao secundario" href="/bipagem/devolver_fornecedor">Bipar mais itens</a>
      <form method="post" :action="`/almoxarifado/devolucao-fornecedor/${dv.id_devolucao}/finalizar`" style="margin:0">
        <button class="botao" :disabled="!dv.qtd_itens">Finalizar devolução</button>
      </form>
    </div>
    <div v-else class="aviso sucesso">Finalizada em {{ f.dataHoraBr(dv.finalizada_em) }} por {{ dv.finalizada_por }}.</div>

    <div class="cartao">
      <h2>{{ dv.qtd_itens }} item(ns) · {{ dv.valor_br }}</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>AGHU</th><th>Material</th><th>Lote</th><th>Nº série</th><th>Validade</th><th>NF</th>
                     <th>Motivo</th><th>Bipado</th><th>Situação</th><th></th></tr></thead>
          <tbody>
            <tr v-for="i in itens" :key="i.id" :style="i.situacao !== 'ativo' ? 'opacity:.55' : ''">
              <td class="mono">{{ i.codigo_aghu || '—' }}</td>
              <td>{{ i.descricao }}<br><a class="pequeno" :href="`/consultas/item/${i.id_unidade}`">histórico</a></td>
              <td class="mono">{{ i.nLote || '—' }}</td>
              <td class="mono">{{ i.numero_serie || '—' }}</td>
              <td>{{ i.validade }}</td>
              <td>{{ i.numero_nf || '—' }}</td>
              <td class="pequeno">{{ i.motivo || '—' }}</td>
              <td class="pequeno">{{ i.quando }} · {{ i.adicionado_por }}</td>
              <td><span v-if="i.situacao === 'ativo'" class="etiqueta verde">na devolução</span>
                  <span v-else class="etiqueta cinza" :title="i.motivo_cancelamento || ''">{{ i.situacao === 'cancelado' ? 'cancelado' : 'desfeito' }}</span></td>
              <td>
                <details v-if="i.situacao === 'ativo' && dv.status !== 'cancelada'" class="pequeno">
                  <summary style="cursor:pointer">tirar</summary>
                  <form method="post" :action="`/almoxarifado/devolucao-fornecedor/${dv.id_devolucao}/cancelar-item`"
                        style="display:flex;gap:.3rem;margin-top:.3rem"
                        data-confirmar="Tirar este item da devolução? Ele volta ao estoque.">
                    <input type="hidden" name="id_unidade" :value="i.id_unidade">
                    <input type="text" name="motivo" required minlength="5" placeholder="motivo" style="width:10rem">
                    <button class="botao perigo pequeno">tirar</button>
                  </form>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <details v-if="dv.status !== 'cancelada'" class="cartao">
      <summary style="cursor:pointer"><strong>Cancelar esta devolução</strong>
        <span class="pequeno suave"> — todos os itens voltam ao estoque (almoxarifado ou farmácia de onde saíram)</span></summary>
      <form method="post" :action="`/almoxarifado/devolucao-fornecedor/${dv.id_devolucao}/cancelar`"
            class="filtros" style="margin-top:.6rem"
            :data-confirmar="`Cancelar a devolução ${dv.id_devolucao}? Os itens voltam ao estoque.`">
        <div class="campo" style="flex:1 1 300px"><label class="obrigatorio">Motivo</label>
          <input type="text" name="motivo" required minlength="5" placeholder="Ex.: fornecedor não retirou / devolução errada"></div>
        <button class="botao perigo">Cancelar devolução</button>
      </form>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const dv = computed(() => props.d.dev);
const itens = computed(() => props.d.itens || []);
</script>
