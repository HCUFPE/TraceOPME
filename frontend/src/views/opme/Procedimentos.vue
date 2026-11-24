<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Procedimentos</h1>
        <p>Procedimentos do dia, para todas as áreas. Abra aqui o procedimento que não veio na agenda.</p>
      </div>
      <div class="acoes"><a class="botao" href="#novo">Abrir procedimento</a></div>
    </div>

    <form method="get" action="/procedimentos" class="cartao" style="display:flex;gap:.6rem;align-items:flex-end;flex-wrap:wrap">
      <div class="campo" style="margin:0"><label>Data</label>
        <input type="date" name="data" :defaultValue="d.data"></div>
      <div class="campo" style="margin:0"><label>Unidade</label>
        <select name="unidade">
          <option value="">todas</option>
          <option v-for="(u, chave) in f.todasUnidades()" :key="chave" :value="chave" :selected="chave === d.unidade">{{ u?.rotulo }}</option>
        </select></div>
      <div class="campo" style="margin:0"><label>Sala</label>
        <input type="text" name="sala" :defaultValue="d.sala" style="width:5rem"></div>
      <div class="campo" style="margin:0"><label>Prontuário ou paciente</label>
        <input type="text" name="prontuario" :defaultValue="d.prontuario"></div>
      <button class="botao secundario">Filtrar</button>
    </form>

    <div class="cartao">
      <h2>{{ f.dataBr(d.data) }} — {{ d.atendimentos.length }} procedimento(s)</h2>
      <div v-if="d.atendimentos.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Hora</th><th>Local</th><th>Prontuário</th><th>Paciente</th><th>OPME solicitado</th>
                     <th>Situação</th><th></th></tr></thead>
          <tbody>
            <tr v-for="a in d.atendimentos" :key="a.id_atendimento">
              <td class="pequeno">{{ a.hora_inicio || '—' }}</td>
              <td class="pequeno">{{ f.rotuloUnidade(a.unidade) }} — sala {{ a.sala }}</td>
              <td><strong>{{ a.prontuario }}</strong></td>
              <td class="pequeno">{{ a.paciente || '—' }}</td>
              <td class="pequeno" style="max-width:20rem;white-space:pre-wrap"><template v-if="sol(a)"><a :href="`/sala-procedimento/atendimento/${a.id_atendimento}#solicitacao`"><span :class="['etiqueta', sol(a).cancelada || sol(a).finalizada ? 'cinza' : !sol(a).faltando ? 'verde' : 'amarelo']">solicitação: {{ sol(a).cancelada ? 'cancelada' : sol(a).atendidas + '/' + sol(a).linhas + ' atendido(s)' + (sol(a).finalizada ? ' · finalizada' : '') }}</span></a><template v-if="sol(a).nao_solicitados"> <span class="etiqueta vermelho">{{ sol(a).nao_solicitados }} sem solicitação</span></template><br v-if="a.opme_solicitado"></template>{{ a.opme_solicitado || (sol(a) ? '' : '—') }}</td>
              <td class="pequeno">
                <span v-if="a.status !== 'aberto'" class="etiqueta cinza">{{ a.status }}</span>
                <span v-if="a.qtd_transito" class="etiqueta amarelo">{{ a.qtd_transito }} aguardando a sala</span>
                <span v-if="a.qtd_na_sala" class="etiqueta verde">{{ a.qtd_na_sala }} na sala</span>
                <span v-if="a.qtd_utilizados" class="etiqueta azul">{{ a.qtd_utilizados }} usado(s)</span>
              </td>
              <td style="white-space:nowrap">
                <a v-if="a.status === 'aberto' && auth.podeAcessar('farmacia')" class="botao pequeno" :href="`/bipagem/dispensar_sala?atendimento=${a.id_atendimento}`">Dispensar</a>
                <template v-if="auth.podeAcessar('sala-procedimento')">
                  <a v-if="a.status === 'aberto' && !a.uso_finalizado_em" class="botao pequeno secundario" :href="`/sala-procedimento/atendimento/${a.id_atendimento}/solicitacao`"> Solicitar OPME</a>
                  <a v-if="a.status === 'aberto'" class="botao pequeno" :href="`/bipagem/registrar_uso?atendimento=${a.id_atendimento}`"> Registrar uso</a>
                  <a class="botao pequeno secundario" :href="`/sala-procedimento/atendimento/${a.id_atendimento}`"> Ficha</a>
                  <a v-if="a.status === 'aberto' && !a.qtd_utilizados && !a.uso_finalizado_em" class="botao pequeno secundario"
                     :href="`/sala-procedimento/atendimento/${a.id_atendimento}#cancelar`" title="Procedimento cancelado: o material dispensado volta direto para a farmácia"> Cancelado</a>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum procedimento nesta data com os filtros atuais. Abra abaixo ou importe a agenda.</p>
    </div>

    <div class="grade grade-2" id="novo">
      <form method="post" action="/procedimentos" class="cartao">
        <h2>Abrir procedimento</h2>
        <p class="suave pequeno">Para procedimento fora da agenda importada.</p>
        <div class="grade grade-2">
          <div class="campo"><label class="obrigatorio">Prontuário</label>
            <input type="text" name="prontuario" required inputmode="numeric"></div>
          <div class="campo"><label>Paciente <span class="opcional">(opcional)</span></label>
            <input type="text" name="paciente"></div>
          <div class="campo">
            <label class="obrigatorio">Local</label>
            <select name="local" required>
              <option v-for="(l, n) in d.locais" :key="n" :value="`${l[0]}|${l[1]}`">{{ l[2] }}</option>
            </select>
          </div>
          <div class="campo">
            <label class="obrigatorio">Especialidade</label>
            <select name="especialidade" required>
              <option value="">— escolha —</option>
              <option v-for="(e, n) in d.especialidades_hospital" :key="n" :value="e[0]">{{ e[1] }}</option>
            </select>
          </div>
          <div class="campo"><label class="obrigatorio">Data</label>
            <input type="date" name="data_procedimento" :defaultValue="d.data" required></div>
          <div class="campo"><label>Hora prevista</label>
            <input type="text" name="hora_inicio" placeholder="07:30"></div>
        </div>
        <div class="campo">
          <label>OPME solicitado <span class="opcional">(opcional)</span></label>
          <textarea name="opme_solicitado" rows="2" placeholder="O que a equipe pediu"></textarea>
        </div>
        <div class="linha-botoes">
          <button v-if="auth.podeAcessar('farmacia')" class="botao" name="seguir" value="dispensar">Abrir e dispensar</button>
          <button v-if="auth.podeAcessar('sala-procedimento')" class="botao" name="seguir" value="solicitar">Abrir e solicitar OPME</button>
          <button v-if="auth.podeAcessar('sala-procedimento')" class="botao" name="seguir" value="uso">Abrir e registrar uso</button>
          <button class="botao secundario">Abrir</button>
        </div>
      </form>

      <!-- nov/2026: agenda direto do relatórios (Metabase), sem baixar CSV. -->
      <form method="post" action="/procedimentos/agenda/buscar" class="cartao" id="agenda-metabase"
            style="border-left:5px solid var(--azul)">
        <h2>Buscar agenda no relatórios</h2>
        <p class="pequeno" style="margin:0 0 .6rem">Traz os procedimentos do dia do relatório
          <strong>Escala prévia definitiva</strong> (modelo {{ ag.modelo }}) e importa na hora. Não duplica o que já existe.</p>
        <div v-if="ag.automatica" class="aviso sucesso pequeno" style="margin:0 0 .6rem">
          Rotina diária ligada: busca sozinha às <strong>{{ ag.horarios.join(', ') }}</strong>
          ({{ ag.dias.map((x: number) => x === 0 ? 'hoje' : x === 1 ? 'amanhã' : `+${x} dias`).join(' e ') }}).</div>
        <div>
          <div class="campo"><label for="agenda-data">Dia</label>
            <input type="date" id="agenda-data" name="data" :defaultValue="d.data"></div>
          <template v-if="!ag.configurada">
            <div class="campo"><label for="agenda-usuario">Usuário de rede</label>
              <input type="text" id="agenda-usuario" name="usuario_rede" :defaultValue="auth.user?.username" autocomplete="username"></div>
            <div class="campo"><label for="agenda-senha" class="obrigatorio">Senha de rede</label>
              <input type="password" id="agenda-senha" name="senha" required autocomplete="current-password">
              <div class="dica">Usada só nesta busca; não fica gravada.</div></div>
          </template>
        </div>
        <button class="botao">Buscar e importar</button>
        <details v-if="ag.ultimas?.length" style="margin-top:.8rem">
          <summary class="pequeno" style="cursor:pointer">Últimas buscas</summary>
          <ul class="pequeno" style="margin:.4rem 0 0 1rem;padding:0">
            <li v-for="b in ag.ultimas" :key="b.id_busca">
              {{ f.dataHoraBr(b.quando) }} · dia {{ f.dataBr(b.dia) }} · {{ b.origem === 'automatica' ? `rotina ${b.horario}` : b.usuario }} ·
              <span :class="['etiqueta', b.ok ? 'verde' : 'vermelho']">{{ b.ok ? 'ok' : 'falhou' }}</span>
              <span class="suave">{{ b.mensagem }}</span></li>
          </ul>
        </details>
      </form>

      <form method="post" action="/procedimentos/agenda" enctype="multipart/form-data" class="cartao">
        <h2>Importar agenda (arquivo CSV)</h2>
        <div class="campo">
          <label>Arquivo CSV</label>
          <input type="file" name="arquivo" accept=".csv,text/csv" required>
          <div class="dica">
            Aceita o export do AGHU direto, sem edição: reconhece as colunas
            <span class="mono">prontuario</span>, <span class="mono">sala</span>,
            <span class="mono">descricao_unidade_funcional</span>,
            <span class="mono">dthr_inicio_cirg</span> e <span class="mono">especialidade</span>,
            e extrai o pedido de OPME de <span class="mono">solicitacao_especial</span>.
          </div>
        </div>
        <p class="suave pequeno">Reimportar o mesmo arquivo não duplica.</p>
        <button class="botao secundario">Importar</button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const ag = computed(() => props.d.agenda_metabase || { configurada: false, automatica: false, horarios: [], dias: [0], ultimas: [] });
const { f, auth } = useTela();
function sol(a: any) { return props.d.solicitacoes?.[a.id_atendimento]; }
</script>
