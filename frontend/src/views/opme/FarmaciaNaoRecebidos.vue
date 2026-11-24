<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Não recebidos pela sala</h1>
        <p>Itens que a farmácia dispensou e a sala informou que <strong>não recebeu</strong>. Eles ficam fora do estoque
           disponível até a farmácia conferir: se localizar o material, volta ao estoque; se estava na sala, registra o
           recebimento; se não localizar, registra o extravio (divergência). Só a farmácia dona do material faz a conferência.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>
    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />
    <p class="pequeno">
      <template v-if="d.filtrando">Mostrando só esta farmácia · <a href="/farmacia/nao-recebidos?todas=1">ver todas</a></template>
      <template v-else>Mostrando todas as farmácias.</template>
    </p>
    <p v-if="!d.unidade_atual && d.itens.length" class="aviso alerta">Escolha acima a farmácia em que você está trabalhando para conferir.</p>
    <div class="cartao">
      <p v-if="!d.itens.length" class="vazio">Nenhum item aguardando conferência.</p>
      <div v-else class="tabela-rolagem"><table>
        <thead><tr><th>Material</th><th>Lote / validade</th><th>Paciente</th><th>Informado</th><th>Conferência</th></tr></thead>
        <tbody>
          <tr v-for="i in d.itens" :key="i.id_unidade">
            <td>{{ i.descricao }}<br><span class="mono pequeno suave">AGHU {{ i.codigo_aghu || '—' }}<template v-if="i.id_caixa"> · caixa {{ i.id_caixa }}</template></span></td>
            <td class="mono pequeno">{{ i.nLote || '—' }}<br>{{ f.dataBr(i.dVal) || '—' }}</td>
            <td class="pequeno">{{ i.prontuario || '—' }}<template v-if="i.paciente"> · {{ i.paciente }}</template><template v-if="i.sala"><br>Sala {{ i.sala }}</template></td>
            <td class="pequeno">{{ f.dataHoraBr(i.informado_em) }}<br><span class="suave">{{ i.informado_por }}</span></td>
            <td>
              <p v-if="d.unidade_atual && i.farmacia && i.farmacia !== d.unidade_atual" class="pequeno suave" style="margin:0">
                Material de outra farmácia — a conferência é feita por ela.</p>
              <form v-else method="post" :action="`/farmacia/nao-recebidos/${i.id_unidade}`" style="display:flex;flex-direction:column;gap:.3rem;margin:0">
                <p v-if="finalizado(i)" class="pequeno" style="margin:0;color:var(--vinho, #7a1f2b)">
                  A sala já finalizou o registro de uso deste paciente.</p>
                <select name="acao" required :disabled="!d.unidade_atual">
                  <option value="">— o que aconteceu? —</option>
                  <option v-for="[chave, rot] in Object.entries(d.acoes || {})" :key="chave" :value="chave"
                          :disabled="!permitida(i, String(chave))">{{ rot }}</option>
                </select>
                <input type="text" name="motivo" :disabled="!d.unidade_atual"
                       :placeholder="finalizado(i) ? 'onde estava e quem recolheu / o que foi verificado' : 'o que foi verificado (obrigatório no extravio)'">
                <button class="botao pequeno" :disabled="!d.unidade_atual">Registrar</button>
              </form>
            </td>
          </tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
// v18.4.5: "estava na sala" só com o registro de uso aberto; depois da finalização,
// a tratativa é "recolhido à farmácia", com o local informado.
const finalizado = (i: any) => !!i.id_atendimento && (i.status_atendimento !== 'aberto' || !!i.uso_finalizado_em);
function permitida(i: any, acao: string): boolean {
  if (acao === 'na_sala') return i.status_atendimento === 'aberto' && !i.uso_finalizado_em;
  if (acao === 'recolhido_apos_finalizacao') return finalizado(i);
  return true;
}
</script>
