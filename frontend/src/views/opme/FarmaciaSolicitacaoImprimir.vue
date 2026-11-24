<template>
  <div class="folha">
    <!-- v18.28: folha de separação. A farmácia imprime e separa o material com
         a lista na mão. Tudo que é navegação some na impressão (@media print). -->
    <div class="cabecalho-pagina sem-imprimir">
      <div>
        <h1>Folha de separação</h1>
        <p>A lista do pedido numa folha, para separar o material com ela na mão.</p>
      </div>
      <div class="acoes">
        <button class="botao" @click="imprimir">Imprimir</button>
        <a class="botao secundario" :href="`/bipagem/dispensar_sala?atendimento=${at.id_atendimento}`">Atender</a>
        <a class="botao secundario" href="/farmacia/solicitacoes">Voltar</a>
      </div>
    </div>

    <div class="cartao papel">
      <div class="topo">
        <div>
          <h2>Pedido de OPME — prontuário {{ at.prontuario }}</h2>
          <p class="pequeno" style="margin:.15rem 0 0">
            {{ at.paciente || 'Paciente não informado' }}
          </p>
          <p class="pequeno suave" style="margin:.15rem 0 0">
            {{ f.rotuloUnidade(at.unidade) }} — Sala {{ at.sala }} ·
            {{ f.especialidade(at.especialidade) }} ·
            {{ f.dataBr(at.data_procedimento) }}<template v-if="at.hora_inicio"> às {{ at.hora_inicio }}</template>
          </p>
          <p class="pequeno suave" style="margin:.15rem 0 0">
            Pedido por {{ d.sol.criado_por || '—' }} · atualizado em {{ d.sol.atualizado_em || '—' }}
          </p>
        </div>
        <div class="pequeno suave direita">
          Impresso em {{ d.impresso_em }}<br>
          {{ d.sol.qtd_faltando }} de {{ d.sol.qtd_linhas }} item(ns) ainda por atender
        </div>
      </div>

      <table class="lista">
        <thead>
          <tr>
            <th style="width:2.2rem">✓</th>
            <th style="width:5rem">AGHU</th>
            <th>Material</th>
            <th style="width:4rem">Qtd.</th>
            <th style="width:5rem">Já dado</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in d.sol.linhas" :key="l.id_item" :class="{ atendido: l.status === 'atendido' }">
            <td class="quadro"><span class="caixinha"></span></td>
            <td class="mono pequeno">{{ l.codigos || '—' }}</td>
            <td>
              {{ l.descricao }}
              <div v-if="l.especificacao" class="pequeno suave">{{ l.especificacao }}</div>
              <div v-if="l.formulario_titulo" class="pequeno suave">{{ l.formulario_titulo }}</div>
            </td>
            <td class="centro"><strong>{{ l.quantidade }}</strong></td>
            <td class="centro pequeno">{{ l.dispensado }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!d.sol.linhas?.length" class="vazio">Este procedimento não tem itens pedidos.</p>

      <p v-if="d.sol.observacao" class="observacao"><strong>Observação da sala:</strong> {{ d.sol.observacao }}</p>

      <div class="assinaturas">
        <div>Separado por: __________________________ &nbsp; Hora: _________</div>
        <div>Conferido por: _________________________ &nbsp; Hora: _________</div>
      </div>
      <p class="pequeno suave rodape">
        Esta folha é apoio para a separação. O registro vale pela bipagem na dispensação.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const at = computed(() => props.d.atendimento || {});

function imprimir() {
  window.print();
}
</script>

<style scoped>
.papel { background: #fff; color: #111; }
.topo { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap;
        border-bottom: 2px solid #111; padding-bottom: .5rem; margin-bottom: .6rem; }
.topo h2 { margin: 0; }
.direita { text-align: right; }
.lista { width: 100%; border-collapse: collapse; }
.lista th, .lista td { border: 1px solid #999; padding: .35rem .4rem; vertical-align: top; text-align: left; }
.lista th { background: #f1f1f1; }
.lista td.centro, .lista th.centro { text-align: center; }
.quadro { text-align: center; }
.caixinha { display: inline-block; width: 1rem; height: 1rem; border: 1.5px solid #333; border-radius: 2px; }
.atendido { background: #f6f6f6; }
.observacao { margin: .7rem 0 0; padding: .4rem .5rem; border-left: 3px solid #999; }
.assinaturas { margin-top: 1.4rem; display: grid; gap: .9rem; }
.rodape { margin-top: .8rem; }

@page { size: A4 portrait; margin: 12mm; }
@media print {
  .sem-imprimir { display: none !important; }
  .folha { width: 100%; max-width: none; margin: 0; padding: 0; }
  .topo { padding-right: 0; }
  .papel { border: 0; box-shadow: none; padding: 0; }
  .lista { font-size: 11pt; }
  .atendido { background: transparent; }
  .lista tr { page-break-inside: avoid; }
}
</style>
