<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Lote {{ b.nLote }}</h1>
        <p>{{ b.motivo }}<template v-if="b.referencia"> · referência {{ b.referencia }}</template></p>
      </div>
      <div class="acoes">
        <button type="button" class="botao secundario" @click="imprimir">Imprimir</button>
        <a class="botao secundario" href="/consultas/recall"> Voltar</a>
      </div>
    </div>

    <div :class="['aviso', b.status === 'ativo' ? 'erro' : 'sucesso']">
      <template v-if="b.status === 'ativo'">
        <strong>Bloqueado</strong> desde {{ f.dataHoraBr(b.criado_em) }}
        por {{ b.criado_por }}. O sistema recusa qualquer movimentação
        deste lote em direção ao paciente.
      </template>
      <template v-else>
        <strong>Liberado</strong> em {{ f.dataHoraBr(b.liberado_em) }}
        por {{ b.liberado_por }}: {{ b.motivo_liberacao }}
      </template>
    </div>

    <div class="cartao">
      <div class="entre">
        <h2>1. Retirar de circulação — {{ d.em_circulacao.length }} unidade(s)</h2>
        <span class="suave pequeno">o que ainda dá para impedir</span>
      </div>
      <template v-if="d.em_circulacao.length">
        <div class="tabela-rolagem">
          <table>
            <thead><tr><th>Onde está</th><th>Produto</th><th>Código</th>
                       <th>Validade</th><th>Paciente reservado</th><th></th></tr></thead>
            <tbody>
              <tr v-for="u in d.em_circulacao" :key="u.id_unidade">
                <td><span :class="['etiqueta', f.corStatus(u.status)]">{{ u.situacao }}</span>
                    <template v-if="u.farmacia"><br><span class="suave pequeno">{{ f.rotuloUnidade(u.farmacia) }}</span></template></td>
                <td>{{ u.xProd }}</td>
                <td class="mono pequeno">{{ u.codigo_barras }}<br>
                    <span class="suave">AGHU {{ u.codigo_aghu || '—' }}</span></td>
                <td class="pequeno">{{ f.dataBr(u.dVal) || '—' }}</td>
                <td class="pequeno">{{ u.prontuario || '—' }}
                    <template v-if="u.sala"><br><span class="suave">sala {{ u.sala }}</span></template></td>
                <td><a class="pequeno" :href="`/consultas/item/${u.id_unidade}`">histórico</a></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="suave pequeno" style="margin-top:.75rem">
          Recolha fisicamente e registre a saída em <em>Almoxarifado → Devolver ao fornecedor</em>
          ou <em>Baixar item</em>. Essas operações continuam liberadas de propósito — são o
          caminho para tirar o lote de circulação.
        </p>
      </template>
      <p v-else class="aviso sucesso" style="margin:0">
        Nenhuma unidade deste lote em circulação. Nada a recolher.
      </p>
    </div>

    <div class="cartao">
      <div class="entre">
        <h2>2. Pacientes que já receberam — {{ d.implantadas.length }}</h2>
        <span class="suave pequeno">para acompanhamento clínico</span>
      </div>
      <template v-if="d.implantadas.length">
        <div class="aviso erro">
          Estes pacientes precisam entrar na lista de acompanhamento do recall.
        </div>
        <div class="tabela-rolagem">
          <table>
            <thead><tr><th>Prontuário</th><th>Paciente</th><th>Data do procedimento</th>
                       <th>Produto</th><th>Nº série</th><th>NF</th><th></th></tr></thead>
            <tbody>
              <tr v-for="u in d.implantadas" :key="u.id_unidade">
                <td><a :href="`/consultas/prontuario?numero=${encodeURIComponent(u.prontuario || '')}`">{{ u.prontuario || '—' }}</a></td>
                <td>{{ u.paciente || '—' }}</td>
                <td>{{ f.dataBr(u.data_procedimento) || '—' }}
                    <span class="suave pequeno"> {{ f.dataHoraBr(u.data_uso) }}</span></td>
                <td class="pequeno">{{ u.xProd }}</td>
                <td class="mono pequeno">{{ u.numero_serie || '—' }}</td>
                <td class="pequeno">{{ u.numero_nf || '—' }}</td>
                <td><a class="pequeno" :href="`/consultas/item/${u.id_unidade}`">histórico</a></td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
      <p v-else class="aviso sucesso" style="margin:0">
        Nenhuma unidade deste lote foi implantada em paciente.
      </p>
    </div>

    <form v-if="b.status === 'ativo'" method="post" :action="`/consultas/recall/${b.id_bloqueio}/liberar`" class="cartao"
          data-confirmar="Liberar o lote? O material volta a circular normalmente.">
      <h2>Liberar o lote</h2>
      <p class="suave pequeno">
        Use quando o fornecedor cancelar o recall ou quando todo o material afetado já
        tiver saído do estoque. O bloqueio continua no histórico.
      </p>
      <div class="campo" style="max-width:560px">
        <label class="obrigatorio">Motivo da liberação</label>
        <input type="text" name="motivo" required
               placeholder="Ex.: fornecedor cancelou o recall — comunicado 15/2026">
      </div>
      <button class="botao secundario">Liberar lote</button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const b = computed(() => props.d.bloqueio);
function imprimir() { window.print(); }
</script>
