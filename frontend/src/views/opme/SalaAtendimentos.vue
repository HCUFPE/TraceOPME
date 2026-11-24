<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Atendimentos</h1>
        <p>Escolha o paciente para {{ f.tituloOperacao(d.operacao) ? f.tituloOperacao(d.operacao).toLowerCase() : 'trabalhar' }}.
           Se ele não estiver na lista, abra em Procedimentos.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/sala-procedimento">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" />

    <div v-if="d.disp_pendentes?.length" class="cartao" style="border-left:6px solid var(--amarelo, #d97706);background:var(--amarelo-claro, #fff7e6)">
      <h2 style="margin-top:0">Material dispensado pela farmácia aguardando sua confirmação ({{ d.disp_pendentes.length }})</h2>
      <p class="pequeno" style="margin:.2rem 0 .6rem">Confira os materiais e confirme o recebimento com seu usuário. Enquanto não confirmar, <strong>aquele prontuário não registra uso</strong> (os outros da sala seguem normalmente).
        Não crie outro procedimento: confirme o recebimento aqui.</p>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Procedimento</th><th>Local</th><th>Paciente</th><th class="num">Itens</th><th>Dispensado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="x in d.disp_pendentes" :key="x.id_dispensacao">
            <td><strong>{{ x.prontuario }}</strong><br><span class="suave pequeno">procedimento de {{ f.dataBr(x.data_procedimento) }}</span></td>
            <td class="pequeno">{{ f.rotuloUnidade(x.unidade) }} — sala {{ x.sala }}</td>
            <td class="pequeno">{{ x.paciente || '—' }}</td>
            <td class="num">{{ x.qtd }}</td>
            <td class="pequeno">{{ f.dataHoraBr(x.criado_em) }} · {{ x.criado_por }}</td>
            <td style="white-space:nowrap">
              <a class="botao pequeno" :href="`/dispensacoes/${x.id_dispensacao}`">Confirmar recebimento</a>
              <a class="botao pequeno secundario" :href="`/sala-procedimento/atendimento/${x.id_atendimento}`"> Ficha</a>
            </td>
          </tr>
        </tbody>
      </table></div>
    </div>

    <div v-if="d.nao_recebidos?.length" class="cartao" id="nao-recebidos" style="border-left:6px solid var(--vermelho, #b3261e)">
      <h2 style="margin-top:0">Conferir: a farmácia não recebeu de volta ({{ d.nao_recebidos.length }})</h2>
      <p class="pequeno" style="margin:.2rem 0 .6rem">Material da lista de não utilizados que não chegou à farmácia.
        Se foi usado no paciente, bipe no prontuário; se está na sala, leve à farmácia. Quem conclui é a farmácia.</p>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Procedimento</th><th>Local</th><th>Paciente</th><th class="num">Itens</th><th></th></tr></thead>
        <tbody>
          <tr v-for="a in d.nao_recebidos" :key="a.id_atendimento">
            <td><strong>{{ a.prontuario }}</strong><br><span class="suave pequeno">procedimento de {{ f.dataBr(a.data_procedimento) }}</span></td>
            <td class="pequeno">{{ f.rotuloUnidade(a.unidade) }} — sala {{ a.sala }}</td>
            <td class="pequeno">{{ a.paciente || '—' }}</td>
            <td class="num">{{ a.pendentes }}</td>
            <td style="white-space:nowrap">
              <a class="botao pequeno" :href="`/sala-procedimento/atendimento/${a.id_atendimento}`">Conferir</a>
              <a class="botao pequeno secundario" :href="`/bipagem/registrar_uso?atendimento=${a.id_atendimento}`"> Bipar uso</a>
            </td>
          </tr>
        </tbody>
      </table></div>
    </div>

    <form method="get" action="/sala-procedimento/atendimentos" class="cartao">
      <div class="filtros">
        <div class="campo"><label>Data do procedimento</label><input type="date" name="data" :defaultValue="d.data"></div>
        <div class="campo">
          <label>Unidade</label>
          <select name="unidade">
            <option value="">todas</option>
            <option v-for="(dados, chave) in d.unidades" :key="chave" :value="chave" :selected="d.unidade === chave">{{ dados.rotulo }}</option>
          </select>
        </div>
        <div class="campo"><label>Sala</label>
          <input type="text" name="sala" :defaultValue="d.sala" placeholder="ex.: 03" style="width:90px"></div>
        <div class="campo">
          <label>Turno</label>
          <select name="turno">
            <option value="">todos</option>
            <option v-for="(dados, chave) in d.turnos" :key="chave" :value="chave" :selected="d.turno === chave">
              {{ dados[0] }} ({{ dados[1] }}–{{ dados[2] }})
            </option>
          </select>
        </div>
        <div class="campo"><label>Prontuário ou paciente</label>
          <input type="text" name="prontuario" :defaultValue="d.prontuario"></div>
        <div class="campo">
          <label>Mostrar</label>
          <select name="mostrar">
            <option value="opme" :selected="d.mostrar === 'opme'">só com OPME solicitado</option>
            <!-- v18.30: quem ainda espera material da farmácia. -->
            <option value="pendente" :selected="d.mostrar === 'pendente'">só com pedido pendente</option>
            <option value="todas" :selected="d.mostrar === 'todas'">todas as cirurgias</option>
          </select>
        </div>
        <input type="hidden" name="operacao" :value="d.operacao">
        <button class="botao">Filtrar</button>
      </div>
      <p class="suave pequeno" style="margin:.6rem 0 0">
        <template v-if="d.mostrar === 'pendente'">“Só com pedido pendente”: procedimentos cujo pedido de OPME
          a farmácia ainda não atendeu por inteiro.</template>
        <template v-else>O filtro “só com OPME solicitado” nunca esconde atendimento cadastrado à mão nem os que
          já têm material registrado.</template>
      </p>
    </form>

    <p v-if="outrasDatas.length" class="aviso alerta pequeno" id="a-concluir">
      Falta finalizar o registro de uso em outra(s) data(s):
      <template v-for="(o, n) in outrasDatas" :key="o.data">{{ n ? ' · ' : ' ' }}<a :href="`/sala-procedimento/atendimentos?data=${o.data}&mostrar=todas`">{{ f.dataBr(o.data) }} ({{ o.qtd }})</a></template>
    </p>

    <div class="cartao">
      <h2>{{ f.dataBr(d.data) }} — {{ d.atendimentos.length }} atendimento(s)</h2>
      <div v-if="d.atendimentos.length" class="tabela-rolagem">
        <table>
          <thead>
            <tr><th>Hora</th><th>Local</th><th>Prontuário</th><th>Especialidade</th>
                <th>OPME pedido</th><th class="num">Usados</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="a in d.atendimentos" :key="a.id_atendimento">
              <td class="pequeno">{{ a.hora_inicio || '—' }}</td>
              <td class="pequeno">
                <strong>Sala {{ a.sala }}</strong><br>
                <span :class="['etiqueta', f.corUnidade(a.unidade)]">{{ f.rotuloUnidade(a.unidade) }}</span>
                <template v-if="a.conflito">
                  <br><span class="etiqueta vermelho" title="Há outro atendimento nesta mesma sala e horário — confira o prontuário antes de bipar.">⚠ mesma sala e hora</span>
                </template>
              </td>
              <td><strong>{{ a.prontuario }}</strong><br>
                  <span class="suave pequeno">{{ a.paciente || '' }}</span>
                  <template v-if="a.origem === 'manual'"><br><span class="etiqueta cinza pequeno">cadastrado à mão</span></template>
                  <template v-if="a.status === 'encerrado'"><br><span class="etiqueta cinza pequeno">encerrado</span></template>
                  <template v-if="a.qtd_transito"><br><span class="etiqueta amarelo pequeno">dispensado — aguardando confirmação ({{ a.qtd_transito }})</span></template>
                  <template v-if="a.qtd_na_sala"><br><span class="etiqueta verde pequeno">{{ a.qtd_na_sala }} recebido(s) da farmácia</span></template>
                  <!-- v18.29: dá para ver na lista quais procedimentos já têm pedido de OPME. -->
                  <template v-if="sol(a)"><br>
                    <!-- v18.31: cancelada/finalizada não é pendência: etiqueta cinza. -->
                    <span v-if="sol(a).cancelada" class="etiqueta cinza pequeno"
                          title="A sala cancelou o pedido; a farmácia não tem mais o que atender.">
                      OPME solicitado — pedido cancelado</span>
                    <span v-else-if="sol(a).finalizada" class="etiqueta cinza pequeno"
                          title="A farmácia finalizou a dispensa deste pedido.">
                      OPME solicitado — dispensa finalizada ({{ sol(a).atendidas }}/{{ sol(a).linhas }})</span>
                    <span v-else :class="['etiqueta', 'pequeno', sol(a).faltando ? 'amarelo' : 'verde']"
                          :title="sol(a).faltando ? 'A farmácia ainda não atendeu tudo o que foi pedido.' : 'A farmácia já atendeu todo o pedido.'">
                      OPME solicitado — {{ sol(a).atendidas }}/{{ sol(a).linhas }} atendido(s)</span>
                  </template>
                  <template v-if="aFinalizar.has(a.id_atendimento)"><br><span class="etiqueta vermelho pequeno">falta finalizar o registro de uso</span></template>
                  <template v-if="a.status === 'cancelado'"><br><span class="etiqueta vermelho pequeno" :title="a.detalhe_cancelamento || ''">cancelado — {{ a.motivo_cancelamento }}</span></template></td>
              <td>{{ f.especialidade(a.especialidade) }}</td>
              <td>
                <!-- v18.29: o pedido feito no TraceOPME aparece aqui com link para ver/editar;
                     o texto que vem do AGHU continua embaixo, como sempre. -->
                <a v-if="sol(a)" class="pequeno" :href="`/sala-procedimento/atendimento/${a.id_atendimento}/solicitacao`">
                  {{ sol(a).linhas }} item(ns) pedido(s)</a>
                <span v-if="sol(a) && sol(a).nao_solicitados" class="etiqueta vermelho pequeno">{{ sol(a).nao_solicitados }} sem solicitação</span>
                <details v-if="a.opme_solicitado">
                  <summary class="pequeno" style="cursor:pointer;color:var(--azul)">ver pedido do AGHU</summary>
                  <div class="pequeno mono" style="white-space:pre-wrap;max-width:420px;margin-top:.3rem">{{ a.opme_solicitado }}</div>
                </details>
                <span v-if="!sol(a) && !a.opme_solicitado" class="suave pequeno">—</span>
              </td>
              <td class="num">{{ a.qtd_utilizados || 0 }}</td>
              <td style="white-space:nowrap">
                <a v-if="a.qtd_transito" class="botao pequeno" :href="`/dispensacoes/atendimento/${a.id_atendimento}`">Confirmar recebimento</a>
                <a v-else-if="aFinalizar.has(a.id_atendimento) && d.operacao !== 'devolver_nao_utilizado'" class="botao pequeno secundario"
                   :href="`/sala-procedimento/atendimento/${a.id_atendimento}/concluir`" title="Finalizar registro de uso e devoluções">Finalizar</a>
                <a v-if="f.tituloOperacao(d.operacao) && (a.status === 'aberto' || d.operacao === 'devolver_nao_utilizado')" class="botao pequeno"
                   :href="`/bipagem/${d.operacao}?atendimento=${a.id_atendimento}`"> {{ f.tituloOperacao(d.operacao) }}</a>
                <a v-if="a.status === 'aberto' && !a.uso_finalizado_em" class="botao pequeno secundario"
                   :href="`/sala-procedimento/atendimento/${a.id_atendimento}/solicitacao`"> Solicitar OPME</a>
                <a class="botao pequeno secundario" :href="`/sala-procedimento/atendimento/${a.id_atendimento}`"> Abrir</a>
                <a v-if="a.status === 'aberto' && !a.qtd_utilizados && !a.uso_finalizado_em" class="botao pequeno secundario"
                   :href="`/sala-procedimento/atendimento/${a.id_atendimento}#cancelar`" title="Procedimento cancelado: o material dispensado volta direto para a farmácia"> Cancelado</a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum atendimento nesta data com os filtros atuais.
        Abra em Procedimentos ou importe a agenda lá.</p>
    </div>

    <div class="cartao" id="novo-atendimento">
      <p style="margin:0">O paciente não está na lista? Abra o procedimento em
        <a href="/procedimentos#novo"><strong>Procedimentos → Abrir procedimento</strong></a>
        (agora é geral: a farmácia também abre, para dispensar o OPME).</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

import { computed } from 'vue';

const props = defineProps<{ d: any }>();
function sol(a: any) { return props.d.solicitacoes?.[a.id_atendimento]; }
const { f } = useTela();
// v18.4.5: sem o cartão "Falta finalizar": a lista mostra a etiqueta no próprio
// atendimento; os de outras datas aparecem só como um aviso de uma linha.
const aFinalizar = computed(() => new Set((props.d.a_concluir || []).map((a: any) => a.id_atendimento)));
const outrasDatas = computed(() => {
  const cont: Record<string, number> = {};
  for (const a of props.d.a_concluir || []) if (a.data_procedimento !== props.d.data) cont[a.data_procedimento] = (cont[a.data_procedimento] || 0) + 1;
  return Object.entries(cont).sort().map(([data, qtd]) => ({ data, qtd }));
});
</script>
