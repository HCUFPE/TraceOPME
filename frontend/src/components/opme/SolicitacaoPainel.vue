<template>
  <!-- Solicitação da sala × dispensado pela farmácia. -->
  <div>
    <div v-if="sol.existe && sol.cancelada_em" class="aviso" style="margin:0 0 .5rem;background:var(--cinza-claro)"><strong>Solicitação cancelada</strong>
      em {{ sol.cancelada_em }} por {{ sol.cancelada_por }}<template v-if="sol.motivo_cancelamento"> — {{ sol.motivo_cancelamento }}</template>.
      Nada mais a atender.<template v-if="modo === 'sala'"> Se precisar de material de novo, é só solicitar.</template>
      <template v-if="jaDispensado"><br><strong>{{ jaDispensado }} item(ns) já tinham sido dispensados antes do cancelamento</strong>
        (marcados na lista abaixo). Eles continuam com o paciente: registre o uso ou devolva como não utilizado.</template></div>
    <template v-if="sol.existe">
      <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
        <div style="flex:1 1 auto">
          <strong>Solicitação da sala:</strong>
          <span v-if="sol.cancelada_em" class="etiqueta cinza">cancelada</span>
          <span v-else :class="['etiqueta', !sol.qtd_faltando ? 'verde' : 'amarelo']">{{ sol.qtd_atendidas }} de {{ sol.qtd_linhas }} atendido(s)</span>
          <span v-if="sol.qtd_sem_estoque" class="etiqueta cinza">{{ sol.qtd_sem_estoque }} em falta</span>
          <span v-if="sol.nao_solicitados?.length && !sol.cancelada_em" class="etiqueta vermelho">{{ somaNaoSolicitados }} bipado(s) sem solicitação</span>
          <span class="pequeno suave"> — pedido por {{ sol.criado_por }} · {{ sol.atualizado_em }}</span>
        </div>
        <!-- v18.28: a farmácia pode imprimir a folha para separar o material. -->
        <a v-if="modo === 'farmacia' && !sol.cancelada_em && atendimento.id_atendimento"
           class="botao pequeno secundario"
           :href="`/farmacia/atendimento/${atendimento.id_atendimento}/solicitacao/imprimir`">Imprimir pedido</a>
      </div>
      <p v-if="sol.observacao" class="pequeno" style="margin:.4rem 0 0"><strong>Obs. da sala:</strong> {{ sol.observacao }}</p>
      <!-- v18.12.2: cancelada = nada a atender. A lista do que tinha sido pedido fica
           fechada, como histórico, e sem os botões de atender. -->
      <component :is="sol.cancelada_em ? 'details' : 'div'" class="historico-cancelada">
      <summary v-if="sol.cancelada_em" class="pequeno" style="cursor:pointer">ver o que tinha sido pedido (histórico)</summary>
      <div v-for="(p, ip) in pedidos" :key="p.rodada">
        <!-- v18.43: cada rodada de pedido num bloco próprio. Com uma só, o
             título não aparece — a tela fica igual à de antes. -->
        <div v-if="pedidos.length > 1" class="faixa-pedido">
          <strong>{{ p.titulo }}</strong>
          <span :class="['etiqueta', !p.qtd_faltando ? 'verde' : 'amarelo']">{{ p.qtd_atendidas }} de {{ p.qtd_linhas }}</span>
          <span v-if="p.qtd_sem_estoque" class="etiqueta cinza">{{ p.qtd_sem_estoque }} em falta</span>
        </div>
        <div style="overflow-x:auto"><table :style="ip ? 'margin-top:.2rem' : 'margin-top:.6rem'">
        <thead><tr><th>Situação</th><th>AGHU</th><th>Material solicitado</th>
          <th class="num">Pedido</th><th class="num">Dispensado</th><th></th></tr></thead>
        <tbody>
          <template v-for="l in p.linhas" :key="l.id_item">
            <tr :style="l.status === 'atendido' ? 'background:var(--verde-claro)' : (l.status === 'parcial' ? 'background:var(--amarelo-claro)' : '')">
              <td style="white-space:nowrap">
                <template v-if="sol.cancelada_em">
                  <span class="etiqueta cinza">cancelado</span>
                  <span v-if="l.dispensado" class="etiqueta amarelo">{{ l.dispensado }} já dispensado(s)</span>
                </template>
                <span v-else-if="l.status === 'atendido'" class="etiqueta verde">✔ dispensado</span>
                <span v-else-if="l.status === 'parcial'" class="etiqueta amarelo">parcial</span>
                <span v-else-if="l.status === 'falta'" class="etiqueta cinza">sem estoque</span>
                <span v-else class="etiqueta cinza">aguardando farmácia</span>
              </td>
              <td class="mono pequeno">{{ l.codigos ? l.codigos.replaceAll(' ', ' / ') : '—' }}</td>
              <td class="pequeno">{{ l.descricao }}<template v-if="l.especificacao"> <strong>{{ l.especificacao }}</strong></template>
                <span v-if="l.formulario === 'avulso'" class="etiqueta cinza">fora do formulário</span>
                <template v-if="l.manual"><br><span class="suave">marcado à mão por {{ l.manual_por }}</span></template>
                <template v-if="l.status === 'falta'"><br><span class="suave">falta marcada por {{ l.falta_por }} em {{ l.falta_em }} — {{ l.falta_motivo }}</span></template>
                <template v-for="(v, n) in l.vinculos || []" :key="n"><br><span class="etiqueta azul">{{ l.sem_codigo ? 'associado ao material bipado' : 'atendido com outro código' }}</span>
                  <span class="pequeno"> AGHU {{ v.aghu }} · {{ v.descricao_bipada }} · lote {{ v.lote }} — {{ v.motivo }} ({{ v.vinculado_por }})</span></template></td>
              <td class="num"><strong>{{ l.quantidade }}</strong></td>
              <td class="num">{{ l.dispensado }}</td>
              <td style="text-align:right;white-space:nowrap">
                <form v-if="podeMexer(l) && l.sem_codigo && !l.vinculos?.length" method="post"
                      :action="`/farmacia/atendimento/${atendimento.id_atendimento}/solicitacao/manual/${l.id_item}`" style="display:inline">
                  <input type="hidden" name="atendido" :value="l.manual ? '0' : '1'">
                  <button class="botao secundario pequeno" data-sem-foco="1">{{ l.manual ? 'desmarcar' : 'marcar atendido' }}</button>
                </form>
                <form v-if="podeMexer(l) && l.vinculos?.length" method="post"
                      :action="`/farmacia/atendimento/${atendimento.id_atendimento}/solicitacao/outro-codigo/${l.id_item}`" style="display:inline">
                  <input type="hidden" name="desfazer" value="1">
                  <button class="botao secundario pequeno" data-sem-foco="1">desfazer associação</button>
                </form>
                <!-- v18.43: falta de estoque -->
                <form v-if="podeMexer(l) && l.status === 'falta'" method="post"
                      :action="`/farmacia/atendimento/${atendimento.id_atendimento}/solicitacao/falta/${l.id_item}`" style="display:inline">
                  <input type="hidden" name="desfazer" value="1">
                  <button class="botao secundario pequeno" data-sem-foco="1">desfazer falta</button>
                </form>
              </td>
            </tr>
            <!-- v18.43: associar material bipado — agora também na linha SEM código AGHU -->
            <tr v-if="podeMexer(l) && l.status !== 'atendido' && (sol.nao_solicitados?.length || l.status !== 'falta')">
              <td colspan="6" style="padding-top:0;border-top:0">
                <details v-if="sol.nao_solicitados?.length && !l.vinculos?.length"><summary class="pequeno" style="cursor:pointer;color:var(--azul, #0c3a67)">
                  {{ l.sem_codigo ? `qual material foi dado para “${(l.descricao || '').slice(0, 45)}”?`
                                  : `“${(l.descricao || '').slice(0, 45)}” foi atendido com outro código AGHU?` }}</summary>
                  <form method="post" :action="`/farmacia/atendimento/${atendimento.id_atendimento}/solicitacao/outro-codigo/${l.id_item}`"
                        style="margin:.5rem 0 .3rem;display:flex;gap:.5rem;flex-wrap:wrap;align-items:center">
                    <select name="unidades" required data-sem-foco="1" style="flex:2 1 22rem">
                      <option value="">— escolha o material bipado —</option>
                      <option v-for="(g, n) in sol.nao_solicitados" :key="n" :value="(g.ids || []).join(',')">AGHU {{ g.aghu }} · {{ (g.descricao || '').slice(0, 50) }} · lote {{ g.lote }} ({{ g.quantidade }} unid.)</option>
                    </select>
                    <input type="text" name="motivo" :list="`motivos-outro-codigo-${l.id_item}`" required minlength="5" data-sem-foco="1"
                           :placeholder="l.sem_codigo ? 'motivo (ex.: a sala pediu pelo nome)' : 'motivo (ex.: código AGHU mudou)'" style="flex:1 1 15rem">
                    <datalist :id="`motivos-outro-codigo-${l.id_item}`"><option v-for="m in motivosOutroCodigo || []" :key="m" :value="m"></option></datalist>
                    <button class="botao pequeno" data-sem-foco="1">confirmar</button>
                  </form>
                </details>
                <details v-if="l.status !== 'falta'"><summary class="pequeno" style="cursor:pointer;color:var(--cinza-escuro, #555)">não tem como atender “{{ (l.descricao || '').slice(0, 45) }}”?</summary>
                  <form method="post" :action="`/farmacia/atendimento/${atendimento.id_atendimento}/solicitacao/falta/${l.id_item}`"
                        style="margin:.5rem 0 .3rem;display:flex;gap:.5rem;flex-wrap:wrap;align-items:center">
                    <input type="text" name="motivo" :list="`motivos-falta-${l.id_item}`" required minlength="3" data-sem-foco="1"
                           placeholder="motivo (ex.: sem estoque na farmácia)" style="flex:1 1 20rem">
                    <datalist :id="`motivos-falta-${l.id_item}`"><option v-for="m in motivosFalta || []" :key="m" :value="m"></option></datalist>
                    <button class="botao secundario pequeno" data-sem-foco="1">marcar falta de estoque</button>
                  </form>
                </details>
              </td>
            </tr>
          </template>
        </tbody>
      </table></div>
      </div>
      <div v-if="sol.nao_solicitados?.length && !sol.cancelada_em" class="aviso erro" style="margin-top:.7rem">
        <strong>Bipado sem estar na solicitação</strong> — confira com a sala:
        <ul class="lista" style="margin:.3rem 0 0 1.1rem">
          <li v-for="(g, n) in sol.nao_solicitados" :key="n" class="pequeno"><span class="mono"><strong>AGHU {{ g.aghu }}</strong></span> · {{ g.descricao }} · lote {{ g.lote }} — <strong>{{ g.quantidade }}</strong> unid. ({{ g.motivo }})</li>
        </ul>
      </div>
      </component>
      <p v-if="sol.finalizada_em && sol.motivo_faltas" class="pequeno" style="margin:.6rem 0 0"><strong>Dispensa finalizada com falta</strong> por {{ sol.finalizada_por }} em {{ sol.finalizada_em }} — motivo: {{ sol.motivo_faltas }}</p>
    </template>
    <p v-else class="pequeno suave" style="margin:0">{{ modo === 'farmacia' ? 'A sala ainda não fez a solicitação deste paciente no sistema.' : 'Nenhum material solicitado ainda.' }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{ sol: any; modo: string; atendimento: any;
                            motivosOutroCodigo?: string[]; motivosFalta?: string[] }>();

// v18.43: o item atendido sobe para o topo do seu pedido. Quem dispensa bipa e
// confere na hora, sem rolar a lista atrás da linha que acabou de atender.
const ORDEM: Record<string, number> = { atendido: 0, parcial: 1, falta: 3 };
function ordenar(linhas: any[]) {
  return [...(linhas || [])].map((l, i) => ({ l, i }))
    .sort((a, b) => (ORDEM[a.l.status] ?? 2) - (ORDEM[b.l.status] ?? 2) || a.i - b.i)
    .map((x) => x.l);
}
const pedidos = computed(() => {
  const blocos = props.sol.pedidos?.length
    ? props.sol.pedidos
    : [{ rodada: 1, titulo: 'Pedido', linhas: props.sol.linhas || [],
         qtd_linhas: props.sol.qtd_linhas, qtd_atendidas: props.sol.qtd_atendidas,
         qtd_faltando: props.sol.qtd_faltando, qtd_sem_estoque: props.sol.qtd_sem_estoque }];
  return blocos.map((b: any) => ({ ...b, linhas: ordenar(b.linhas) }));
});
function podeMexer(_l: any) {
  return props.modo === 'farmacia' && props.atendimento.status === 'aberto' && !props.sol.cancelada_em;
}
const somaNaoSolicitados = computed(() => (props.sol.nao_solicitados || []).reduce((s: number, g: any) => s + (Number(g.quantidade) || 0), 0));
const jaDispensado = computed(() => (props.sol.linhas || []).reduce((s: number, l: any) => s + (Number(l.dispensado) || 0), 0));
</script>

<style scoped>
.historico-cancelada > summary { padding: .3rem 0; color: var(--azul, #0c3a67); }
.faixa-pedido { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap;
  margin: .9rem 0 .1rem; padding-top: .6rem; border-top: 1px solid rgba(0,0,0,.12); }
</style>
