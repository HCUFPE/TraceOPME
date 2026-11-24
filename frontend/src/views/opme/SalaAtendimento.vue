<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Prontuário {{ at.prontuario }}</h1>
        <p>{{ (d.descricao || '').replace(`Prontuário ${at.prontuario} · `, '') }}<template v-if="at.paciente"> · {{ at.paciente }}</template></p>
      </div>
      <div class="acoes"><a class="botao secundario" :href="`/sala-procedimento/atendimentos?data=${at.data_procedimento}`">Voltar</a></div>
    </div>

    <div class="trilha">
      <div :class="['etapa', { destaque: r.utilizados }]"><strong>{{ r.utilizados }}</strong> utilizados neste paciente</div>
      <div class="etapa"><strong>{{ r.devolvidos }}</strong> devolvidos sem uso à farmácia</div>
      <div v-if="r.devolucao_aguardando" class="etapa destaque"><strong>{{ r.devolucao_aguardando }}</strong> pendente(s) de devolução —
        aguardando a ciência da farmácia</div>
    </div>

    <!-- v18.3: a sala — abrir, ciência do material, uso, finalizar; e chamar maqueiro / limpeza. -->
    <div v-if="at.status !== 'cancelado'" class="cartao cartao-sala" id="sala">
      <div class="entre" style="flex-wrap:wrap;gap:.6rem;align-items:flex-start">
        <div>
          <h2 style="margin:0">Sala {{ at.sala }}</h2>
          <p v-if="at.sala_aberta_em" class="pequeno" style="margin:.2rem 0 0">Aberta às <strong>{{ String(at.sala_aberta_em).slice(11, 16) }}</strong>
            por {{ at.sala_aberta_por }}<template v-if="at.sala_aberta_auto"> <span class="suave">(registrada sozinha na 1ª ação)</span></template></p>
          <p v-else class="pequeno suave" style="margin:.2rem 0 0">A sala ainda não foi aberta para este paciente.</p>
        </div>
      </div>


      <!-- v18.4.4: uma ação principal por vez — Receber → Utilizar → Finalizar. -->
      <div v-if="at.status === 'aberto'" class="proxima-acao">
        <div class="pa-titulo">Próxima ação</div>
        <ol class="pa-etapas">
          <li v-for="(e, i) in ETAPAS_SALA" :key="e" :class="estadoEtapa(i)">
            <span class="pa-bola">{{ estadoEtapa(i) === 'feito' ? '✓' : i + 1 }}</span>{{ e }}
          </li>
        </ol>
        <div class="pa-corpo">
          <template v-if="etapaAtual === 0 && !at.sala_aberta_em">
            <h3>Abrir sala</h3>
            <p>Quando o paciente entrar, abra a sala. Em seguida você confere o que a farmácia enviou.</p>
            <form method="post" :action="`/sala-procedimento/atendimento/${at.id_atendimento}/abrir-sala`" style="margin:0">
              <button class="botao botao-grande">▶ Abrir sala</button>
            </form>
          </template>
          <template v-else-if="etapaAtual === 0">
            <h3>Confirmar recebimento</h3>
            <p>Confira o que a farmácia enviou ({{ aguardando.length }} item(ns)). Confirme os materiais recebidos e sinalize eventuais faltas.</p>
            <a class="botao botao-grande" :href="`/dispensacoes/atendimento/${at.id_atendimento}`">Confirmar materiais recebidos</a>
          </template>
          <template v-else-if="etapaAtual === 1">
            <h3>Registrar o uso</h3>
            <p>Bipe cada material no momento do uso no paciente. Material que caiu ou veio com problema é sinalizado na própria bipagem.</p>
            <a class="botao botao-grande" :href="`/bipagem/registrar_uso?atendimento=${at.id_atendimento}`">Registrar uso</a>
            <p class="pequeno" style="margin:.7rem 0 0">Terminou a bipagem?
              <a :href="`/sala-procedimento/atendimento/${at.id_atendimento}/concluir`">Finalizar registro de uso e devoluções</a></p>
          </template>
          <template v-else>
            <h3>Sala liberada — aguardando conferência da farmácia</h3>
            <p>Leve os materiais pendentes de devolução à farmácia; ela confere e conclui. A sala já pode receber o próximo paciente.</p>
          <div :class="['aviso', d.pendencias?.total ? 'erro' : 'info']" style="margin:.6rem 0 0">
            <strong>Registro de uso e devoluções finalizado</strong> em {{ f.dataHoraBr(at.uso_finalizado_em) }}
            por {{ at.uso_finalizado_por }}.
            <template v-if="d.lista_na_farmacia">
              A lista de não utilizados está com a farmácia, para conferir e dar ciência. Ela encerra o procedimento.
            </template>
            <template v-else-if="d.pendencias?.total">
              <br><strong>A farmácia não recebeu de volta {{ d.pendencias.total }} item(ns).</strong> Confira:
              se foi usado no paciente, <a :href="`/bipagem/registrar_uso?atendimento=${at.id_atendimento}`">bipe aqui no prontuário</a>;
              se está na sala, leve à farmácia. Quem conclui é a farmácia.
              <ul style="margin:.4rem 0 0 1.1rem">
                <li v-for="(i, n) in d.pendencias.itens" :key="'i' + n"><span class="mono">AGHU {{ i.codigo_aghu || '—' }}</span> · {{ i.descritivo_hospital || i.xProd }} · lote {{ i.nLote || '—' }} · val. {{ f.dataBr(i.dVal) || '—' }}</li>
                <li v-for="(c, n) in d.pendencias.caixas" :key="'c' + n">Caixa <span class="mono">{{ c.id_caixa }}</span> {{ c.nome }} — {{ c.qtd }} item(ns)</li>
              </ul>
            </template>
            <template v-else>Aguardando a farmácia concluir.</template>
          </div>
          <!-- v18.22: sobrou material que não foi bipado nem entrou na lista da farmácia.
               Antes isso só aparecia quando não havia lista pendente — com a lista em
               conferência, a sala não via nada e achava que não podia mais fazer nada. -->
          <div v-if="d.lista_na_farmacia && d.pendencias?.total" class="aviso alerta" style="margin:.6rem 0 0">
            <strong>{{ d.pendencias.total }} material(is) não utilizado(s) ainda não estão na lista da farmácia.</strong>
            Se foi usado no paciente, <a :href="`/bipagem/registrar_uso?atendimento=${at.id_atendimento}`">bipe o uso aqui</a>
            — dá para bipar mesmo com o registro já finalizado. Se não foi usado, leve à farmácia e
            <a :href="`/sala-procedimento/atendimento/${at.id_atendimento}/concluir`">inclua na lista de não utilizados</a>.
            <ul style="margin:.4rem 0 0 1.1rem">
              <li v-for="(i, n) in d.pendencias.itens" :key="'s' + n"><span class="mono">AGHU {{ i.codigo_aghu || '—' }}</span>
                · {{ i.descritivo_hospital || i.xProd }} · lote {{ i.nLote || '—' }} · val. {{ f.dataBr(i.dVal) || '—' }}</li>
              <li v-for="(c, n) in d.pendencias.caixas" :key="'sc' + n">Caixa <span class="mono">{{ c.id_caixa }}</span> {{ c.nome }} — {{ c.qtd }} item(ns)</li>
            </ul>
          </div>
          </template>
        </div>
      </div>

      <!-- v18.13.1: a sala está com outro paciente — este pode assumir quando entrar -->
      <div v-if="at.status === 'aberto' && d.sala_ocupada_por" id="assumir-sala" class="bloco-sec">
        <h3 style="margin:0 0 .3rem">Este paciente entrou na sala agora?</h3>
        <p class="pequeno" style="margin:0 0 .5rem">A sala {{ d.sala_ocupada_por.sala }} está aberta com
          <strong>{{ d.sala_ocupada_por.paciente || d.sala_ocupada_por.prontuario }}</strong>
          (prontuário {{ d.sala_ocupada_por.prontuario }}) desde
          {{ (d.sala_ocupada_por.sala_aberta_em || '').slice(11, 16) }}. Se quem entrou agora é este paciente,
          passe a sala para ele: o material de cada um continua com o seu paciente.</p>
        <form method="post"
              :action="`/sala-procedimento/atendimento/${d.sala_ocupada_por.id_atendimento}/passar-sala`"
              class="linha-botoes" style="align-items:center;flex-wrap:wrap"
              data-confirmar="Passar a sala para este paciente? O material do outro paciente continua reservado para ele.">
          <input type="hidden" name="destino" :value="at.id_atendimento">
          <input type="text" name="motivo" required placeholder="motivo (ex.: paciente anterior saiu da sala)" style="width:21rem">
          <button class="botao secundario pequeno">Assumir a sala</button>
        </form>
      </div>
      <details class="outras-acoes" :open="outrasAbertas">
        <summary>Outras ações: solicitação de OPME, chamar maqueiro ou limpeza, estorno</summary>
        <div id="solicitacao" class="bloco-sec">
          <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap;margin-bottom:.4rem">
            <h3 style="margin:0;flex:1 1 auto">Solicitação de OPME à farmácia</h3>
            <a v-if="at.status === 'aberto' && !d.finalizado" :class="['botao', 'pequeno', { secundario: d.solicitacao?.existe }]"
               :href="`/sala-procedimento/atendimento/${at.id_atendimento}/solicitacao`">{{ d.solicitacao?.existe ? 'Alterar solicitação' : 'Solicitar material' }}</a>
          </div>
          <SolicitacaoPainel :sol="d.solicitacao" modo="sala" :atendimento="at" />
          <!-- v18.7.3: a sala cancela a solicitação (sai da farmácia) -->
          <details v-if="d.solicitacao?.pode_cancelar && at.status === 'aberto' && !d.finalizado" class="cancelar-sol">
            <summary>Cancelar a solicitação de OPME</summary>
            <form method="post" :action="`/sala-procedimento/atendimento/${at.id_atendimento}/solicitacao/cancelar`"
                  class="linha-botoes" style="margin-top:.4rem;align-items:center"
                  data-confirmar="Cancelar a solicitação de OPME? A farmácia deixa de ver este pedido. O que já foi dispensado continua com o paciente.">
              <select name="motivo" required style="width:auto">
                <option value="">— motivo —</option>
                <option>Material não será mais necessário</option>
                <option>Procedimento mudou</option>
                <option>Pedido feito por engano / em duplicidade</option>
                <option>Material já está na sala</option>
                <option>Procedimento suspenso</option>
              </select>
              <button class="botao secundario pequeno">Cancelar solicitação</button>
            </form>
          </details>
          <template v-if="at.opme_solicitado">
            <p class="pequeno" style="margin:.6rem 0 0"><strong>OPME solicitado (agenda):</strong></p>
            <div class="pequeno mono" style="white-space:pre-wrap">{{ at.opme_solicitado }}</div>
          </template>
        </div>
        <p v-if="r.utilizados" class="pequeno bloco-sec" style="margin:.5rem 0">Registrou um uso errado?
          <a :href="`/sala-procedimento/estorno?atendimento=${at.id_atendimento}`">Estornar um uso</a></p>

        <!-- v18.13.1: entrou outro paciente na frente — a SALA passa, o material de cada um fica com ele -->
        <div v-if="at.status === 'aberto' && at.sala_aberta_em" id="passar-sala" class="bloco-sec">
          <h3 style="margin:0 0 .3rem">Entrou outro paciente na frente?</h3>
          <p class="pequeno" style="margin:0 0 .5rem">A <strong>sala {{ at.sala }}</strong> passa a atender o paciente
            escolhido, que bipa o material dele. <strong>Nada de material muda de paciente</strong>: os
            {{ d.troca_itens }} item(ns) deste paciente continuam reservados para ele, no mesmo lugar, e não voltam
            para a farmácia. Quando ele entrar, passe a sala de volta pela ficha dele.</p>
          <form v-if="d.troca_candidatos?.length" method="post"
                :action="`/sala-procedimento/atendimento/${at.id_atendimento}/passar-sala`"
                class="linha-botoes" style="align-items:center;flex-wrap:wrap"
                data-confirmar="Passar a sala para o paciente escolhido? O material deste paciente continua reservado para ele.">
            <select name="destino" required style="width:auto;max-width:26rem">
              <option value="">— quem vai entrar? —</option>
              <option v-for="c in d.troca_candidatos" :key="c.id_atendimento" :value="c.id_atendimento">
                {{ c.prontuario }} · {{ c.paciente || 'sem nome' }} — sala {{ c.sala }}{{ c.hora_inicio ? ' · ' + c.hora_inicio : '' }}
              </option>
            </select>
            <input type="text" name="motivo" required placeholder="motivo (ex.: médico antecipou este paciente)" style="width:19rem">
            <button class="botao secundario pequeno">Passar a sala</button>
          </form>
          <p v-else class="aviso pequeno" style="margin:0">Não há outro procedimento aberto hoje nesta unidade.
            Abra o procedimento do paciente que entrou (em <a href="/procedimentos">Procedimentos</a>) e volte aqui.</p>
        </div>
      <!-- Chamados para o QG da enfermagem -->
      <div id="chamados" class="chamados">
        <h3>Chamar para a sala</h3>
        <div class="linha-chamados">
          <form v-for="(t, chave) in d.tipos_chamado" :key="chave" method="post" class="form-chamado"
                :action="`/sala-procedimento/atendimento/${at.id_atendimento}/chamado`">
            <input type="hidden" name="tipo" :value="chave">
            <div class="cab-chamado"><span class="ic">{{ t.icone }}</span> <strong>{{ t.rotulo }}</strong></div>
            <select name="motivo" required>
              <option v-for="m in t.motivos" :key="m" :value="m">{{ m }}</option>
            </select>
            <input type="text" name="observacao" placeholder="observação (opcional)">
            <button class="botao" :disabled="!!aberto(String(chave))">{{ aberto(String(chave)) ? 'Já chamado' : `Chamar ${t.rotulo.toLowerCase()}` }}</button>
          </form>
        </div>
        <ul v-if="d.chamados?.length" class="lista-chamados">
          <li v-for="c in d.chamados" :key="c.id_chamado" :class="'ch-' + c.status">
            <span class="ic">{{ c.icone }}</span>
            <div style="flex:1">
              <strong>{{ c.tipo_rotulo }}</strong> · {{ c.motivo || '—' }}<template v-if="c.observacao"> — {{ c.observacao }}</template><br>
              <span class="pequeno">
                <template v-if="c.status === 'aberto'">Aguardando o QG há {{ c.espera_min }} min</template>
                <template v-else-if="c.status === 'direcionado'"><strong>{{ c.responsavel }}</strong> a caminho (há {{ c.a_caminho_min }} min)</template>
                <template v-else-if="c.status === 'atendido'">Atendido às {{ String(c.atendido_em).slice(11, 16) }}<template v-if="c.responsavel"> por {{ c.responsavel }}</template></template>
                <template v-else>Cancelado</template>
                · chamado às {{ String(c.criado_em).slice(11, 16) }} por {{ c.criado_por }}</span>
            </div>
            <form v-if="c.status === 'aberto' || c.status === 'direcionado'" method="post" :action="`/sala-procedimento/chamado/${c.id_chamado}/cancelar`"
                  data-confirmar="Cancelar este chamado?">
              <input type="hidden" name="voltar" :value="`/sala-procedimento/atendimento/${at.id_atendimento}`">
              <button class="botao secundario pequeno">cancelar</button>
            </form>
          </li>
        </ul>
      </div>
      </details>
    </div>


    <div class="cartao">
      <h2>Consultas e histórico</h2>
      <div class="linha-botoes">
        <a class="botao secundario" :href="`/consultas/prontuario?numero=${encodeURIComponent(at.prontuario)}`"> Ficha do paciente</a>
        <a class="botao secundario" :href="`/consultas/eventos?prontuario=${encodeURIComponent(at.prontuario)}&tipo=uso_devolucao&inicio=${at.data_procedimento}`"> Histórico de movimentações</a>
      </div>
      <details v-if="d.etapas_sala" class="horarios">
        <summary>Horários da sala</summary>
        <ol v-if="d.etapas_sala" class="passos-sala">
          <li v-for="(e, i) in d.etapas_rotulos" :key="e.chave" :class="passoSala(i)">
            <span class="bola">{{ passoSala(i) === 'feito' ? '✓' : passoSala(i) === 'pulado' ? '–' : i + 1 }}</span>
            <span class="rot">{{ e.rotulo }}</span>
            <span class="hora">{{ d.etapas_sala.horas[e.chave] || '' }}</span>
          </li>
        </ol>
      </details>

      <CancelarProcedimento v-if="at.status === 'aberto' && !r.utilizados && !at.uso_finalizado_em"
                            :acao="`/sala-procedimento/atendimento/${at.id_atendimento}/cancelar`"
                            :dispensados="(r.transito_sala || 0) + (r.na_sala || 0)" :motivos="d.motivos_cancelamento" />

      <div v-if="at.status === 'cancelado'" class="aviso erro" style="margin-top:1rem">
        <strong>Procedimento cancelado</strong> em {{ f.dataHoraBr(at.cancelado_em) }} por
        {{ at.cancelado_por }} — motivo: <strong>{{ at.motivo_cancelamento }}</strong>
        <template v-if="at.detalhe_cancelamento">({{ at.detalhe_cancelamento }})</template>.
        <!-- v18.43: cancelamento por engano se desfaz aqui mesmo, sem supervisão. -->
        <details style="margin-top:.6rem">
          <summary style="cursor:pointer"><strong>Foi engano? Desfazer o cancelamento</strong></summary>
          <form method="post" :action="`/sala-procedimento/atendimento/${at.id_atendimento}/descancelar`"
                style="margin-top:.6rem;display:flex;gap:.5rem;flex-wrap:wrap;align-items:center">
            <input type="text" name="motivo" required minlength="5" style="flex:1 1 22rem"
                   placeholder="motivo (ex.: cancelei o paciente errado)">
            <button class="botao">Desfazer cancelamento</button>
          </form>
          <p class="pequeno suave" style="margin:.5rem 0 0">O procedimento volta a ficar aberto e a
            solicitação da sala volta a valer. O material que já tinha voltado para a farmácia
            <strong>não</strong> volta sozinho: a farmácia dispensa de novo, bipando.</p>
        </details>
      </div>

      <template v-if="at.status !== 'aberto'">
        <p v-if="at.status === 'encerrado'" class="aviso sucesso" style="margin-top:1rem">
          Atendimento encerrado em {{ f.dataHoraBr(at.encerrado_em) }} por {{ at.encerrado_por }}.
        </p>
        <details class="cartao" style="margin-top:.5rem;border-left:5px solid var(--amarelo, #b58100)">
          <summary style="cursor:pointer"><strong>{{ at.status === 'cancelado' ? 'Reabrir mesmo assim' : 'Esqueceu algum material?' }} — com a supervisão</strong></summary>
          <form method="post" :action="`/sala-procedimento/atendimento/${at.id_atendimento}/reabrir`"
                style="margin-top:1rem" autocomplete="off">
            <p class="suave pequeno">A supervisora digita o próprio usuário e senha aqui. Fica registrado quem autorizou e por quê.</p>
            <div class="grade grade-3">
              <div class="campo"><label class="obrigatorio">Usuário da supervisora</label>
                <input type="text" name="usuario_supervisao" required autocomplete="off"></div>
              <div class="campo"><label class="obrigatorio">Senha</label>
                <input type="password" name="senha_supervisao" required autocomplete="new-password"></div>
              <div class="campo"><label class="obrigatorio">Motivo</label>
                <input type="text" name="motivo" required placeholder="Ex.: material esquecido na bipagem"></div>
            </div>
            <button class="botao">Reabrir atendimento</button>
          </form>
        </details>
      </template>

      <div v-if="d.historico_encerramento?.length" class="pequeno suave" style="margin-top:.8rem">
        <template v-for="(h, n) in d.historico_encerramento" :key="n">
          {{ f.dataHoraBr(h.data_evento) }} — {{ ROTULO_HIST[h.tipo] || h.tipo }}
          por {{ h.usuario }}<template v-if="h.motivo"> (motivo: {{ h.motivo }})</template><br>
        </template>
      </div>
    </div>

    <!-- v18.34: material que a farmácia dispensou para este paciente e a sala
         bipou no prontuário de outro. Sem isto a ficha ficava sem rastro. -->
    <!-- v18.37: atalho para trocar a peça registrada no uso. -->
    <div v-if="d.usos_a_corrigir" class="aviso alerta" style="margin:.6rem 0">
      <strong>{{ d.usos_a_corrigir }} uso(s) registrado(s) sem dispensação</strong> têm peça do mesmo
      material parada na sala. Pode ter sido o bipe pegando a unidade errada —
      <a :href="`/sala-procedimento/correcao-uso?atendimento=${at.id_atendimento}`">corrigir o registro</a>.
    </div>

    <div v-if="d.usados_em_outro?.length" class="cartao" style="border-left:4px solid var(--amarelo, #d79a00)">
      <h2>{{ d.usados_em_outro.length }} material(is) usado(s) em outro prontuário</h2>
      <p class="pequeno suave" style="margin:.1rem 0 .6rem">Foram dispensados para este paciente e a sala
        registrou o uso em outro prontuário. Ficam aqui para a conferência do que a farmácia entregou.</p>
      <table class="tabela-simples">
        <thead><tr><th>Material</th><th>Lote</th><th>Usado no prontuário</th><th>Quando</th><th>Por</th></tr></thead>
        <tbody>
          <tr v-for="m in d.usados_em_outro" :key="m.id_unidade">
            <td>{{ m.descritivo_hospital || m.xProd }} <span class="pequeno suave">AGHU {{ m.codigo_aghu || '—' }}</span></td>
            <td class="mono pequeno">{{ m.nLote || '—' }}</td>
            <td><a :href="`/sala-procedimento/atendimento/${m.destino}`">{{ m.prontuario_destino || '—' }}</a></td>
            <td class="pequeno">{{ f.dataHoraBr(m.quando) }}</td>
            <td class="pequeno">{{ m.por }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="d.entregas?.length" class="cartao alerta-entrega-cartao">
      <h2>Caixa a entregar ao paciente</h2>
      <!-- v18.23: a ciência também é dada aqui. Antes só existia na tela de finalizar,
           que fecha depois da finalização — e o atendimento travava sem saída. -->
      <div v-for="(e, n) in d.entregas" :key="n" class="linha-entrega">
        <div><strong>{{ e.descritivo_hospital || e.xProd }}</strong>
          <span class="pequeno suave">AGHU {{ e.codigo_aghu }} · lote {{ e.nLote || '—' }}</span></div>
        <span v-if="e.ciencia_por" class="etiqueta verde">ciente: {{ e.ciencia_por }}, {{ f.dataHoraBr(e.ciencia_em) }}</span>
        <form v-else method="post" style="margin:0"
              :action="`/sala-procedimento/atendimento/${at.id_atendimento}/ciencia/${e.id_unidade}`">
          <button class="botao pequeno">Dar ciência da entrega</button>
        </form>
      </div>
    </div>

    <div v-if="d.dispensados?.length" class="cartao" :style="aguardando.length ? 'border-left:5px solid var(--amarelo, #d97706)' : ''">
      <div class="entre" style="flex-wrap:wrap;gap:.6rem">
        <h2 style="margin:0">Dispensado pela farmácia ({{ d.dispensados.length }})</h2>
        <a v-if="aguardando.length" class="botao" :href="`/dispensacoes/atendimento/${at.id_atendimento}`">Confirmar recebimento ({{ aguardando.length }})</a>
      </div>
      <div class="tabela-rolagem" style="margin-top:.6rem">
        <table>
          <thead><tr><th>Produto</th><th>AGHU</th><th>Lote</th><th>Caixa</th><th>Dispensado</th><th>Recebido na sala</th><th>Situação agora</th></tr></thead>
          <tbody>
            <tr v-for="(x, n) in d.dispensados" :key="n">
              <td>{{ x.descritivo_hospital || x.xProd }}</td>
              <td class="mono pequeno">{{ x.codigo_aghu || '—' }}</td>
              <td class="mono">{{ x.nLote || '—' }}</td>
              <td class="mono pequeno">{{ x.id_caixa || '—' }}</td>
              <td class="pequeno">{{ f.dataHoraBr(x.bipado_em) }}<br><span class="suave">{{ x.bipado_por }}</span></td>
              <td class="pequeno"><span v-if="x.situacao === 'recebido'" class="etiqueta verde">{{ x.recebido_por }}</span>
                  <span v-else-if="x.situacao === 'cancelado'" class="etiqueta cinza">não foi para a sala</span>
                  <span v-else class="etiqueta amarelo">aguardando a confirmação</span></td>
              <td class="pequeno"><template v-if="at.status === 'cancelado' && x.atendimento_atual !== at.id_atendimento"><span class="etiqueta azul">voltou ao estoque da farmácia</span>
                  <br><span class="suave">procedimento cancelado</span></template>
                  <template v-else>{{ f.rotuloStatus(x.status_unidade) }}</template></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="d.devolvidos?.length" class="cartao">
      <h2>Devolvidos sem uso à farmácia ({{ d.devolvidos.length }})</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Produto</th><th>AGHU</th><th>Lote</th><th>Devolvido em</th><th>Devolvido por (sala)</th><th>Recebido por (farmácia)</th></tr></thead>
          <tbody>
            <tr v-for="(x, n) in d.devolvidos" :key="n">
              <td>{{ x.descritivo_hospital || x.xProd }}</td>
              <td class="mono pequeno">{{ x.codigo_aghu || '—' }}</td>
              <td class="mono">{{ x.nLote || '—' }}</td>
              <td class="pequeno">{{ f.dataHoraBr(x.data_evento) }}</td>
              <td class="pequeno"><span class="etiqueta azul">{{ x.devolvido_por || x.bipado_por || '—' }}</span><template v-if="x.bipado_por && x.devolvido_por && x.devolvido_por !== x.bipado_por"><br><span class="suave">login {{ x.bipado_por }}</span></template></td>
              <td class="pequeno"><span v-if="x.recebido_por" class="etiqueta verde">{{ x.recebido_por }}</span><template v-else>—</template></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="cartao">
      <h2>Materiais utilizados</h2>
      <div v-if="d.materiais?.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Produto</th><th>AGHU</th><th>Lote</th><th>Validade</th><th>Nº série</th><th>Situação</th><th>Registrado em</th><th></th></tr></thead>
          <tbody>
            <tr v-for="m in d.materiais" :key="m.id_unidade">
              <td>{{ m.xProd }}<br><span class="suave pequeno">{{ m.fornecedor || '' }}</span></td>
              <td class="mono pequeno">{{ m.codigo_aghu || '—' }}</td>
              <td class="mono">{{ m.nLote || '—' }}</td>
              <td>{{ f.dataBr(m.dVal) || '—' }}</td>
              <td class="mono pequeno">{{ m.numero_serie || '—' }}</td>
              <td><span :class="['etiqueta', f.corStatus(m.status)]">{{ f.rotuloStatus(m.status) }}</span></td>
              <td class="pequeno">{{ f.dataHoraBr(m.ultimo_movimento) }}</td>
              <td><a class="pequeno" :href="`/consultas/item/${m.id_unidade}`">histórico</a></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum material registrado neste atendimento ainda.</p>
    </div>

    <details class="cartao">
      <summary style="cursor:pointer"><strong>Corrigir dados do atendimento</strong></summary>
      <form method="post" :action="`/sala-procedimento/atendimento/${at.id_atendimento}`" style="margin-top:1rem">
        <div class="grade grade-2">
          <div class="campo"><label>Prontuário</label><input type="text" name="prontuario" :defaultValue="at.prontuario"></div>
          <div class="campo"><label>Paciente</label><input type="text" name="paciente" :defaultValue="at.paciente || ''"></div>
          <div class="campo">
            <label>Local</label>
            <select name="local">
              <option v-for="(l, n) in d.locais" :key="n" :value="`${l[0]}|${l[1]}`"
                      :selected="l[0] === at.unidade && l[1] === at.sala">{{ l[2] }}</option>
            </select>
          </div>
          <!-- v18.43.5: a hora do procedimento também se corrige aqui -->
          <div class="campo"><label>Hora do procedimento</label>
            <input type="time" name="hora_inicio" :defaultValue="at.hora_inicio || ''"></div>
          <div class="campo"><label>Observação</label><input type="text" name="observacao" :defaultValue="at.observacao || ''"></div>
        </div>
        <p class="suave pequeno">Prontuário e sala ficam bloqueados depois que houver material registrado como utilizado.</p>
        <button class="botao secundario">Salvar</button>
      </form>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import CancelarProcedimento from '../../components/opme/CancelarProcedimento.vue';
import SolicitacaoPainel from '../../components/opme/SolicitacaoPainel.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const at = computed(() => props.d.atendimento);
const r = computed(() => props.d.resumo || {});
const aguardando = computed(() => (props.d.dispensados || []).filter((x: any) => x.situacao === 'pendente'));
// v18.4.4: três ações principais, na ordem do procedimento.
const ETAPAS_SALA = ['Receber', 'Utilizar', 'Finalizar'];
const etapaAtual = computed(() => {
  if (!at.value?.sala_aberta_em || aguardando.value.length) return 0;
  if (!props.d.finalizado) return 1;
  return 3;
});
function estadoEtapa(i: number): string {
  if (i < etapaAtual.value) return 'feito';
  return i === etapaAtual.value ? 'agora' : '';
}
// v18.3: etapas da sala (feito = tem hora; pulado = ficou para trás sem hora; agora = a próxima).
function passoSala(i: number): string {
  const p = props.d.etapas_sala; const etapas = props.d.etapas_rotulos || [];
  if (!p) return '';
  if (p.horas[etapas[i].chave]) return 'feito';
  const ultima = etapas.reduce((m: number, e: any, j: number) => (p.horas[e.chave] ? j : m), -1);
  if (i < ultima) return 'pulado';
  if (i === ultima + 1 && !['concluido', 'cancelado'].includes(p.etapa)) return 'agora';
  return '';
}
const outrasAbertas = computed(() => (props.d.chamados || []).some((c: any) => ['aberto', 'direcionado'].includes(c.status))
  || (typeof location !== 'undefined' && location.hash === '#solicitacao'));
const aberto = (tipo: string) => (props.d.chamados || []).find((c: any) => c.tipo === tipo && ['aberto', 'direcionado'].includes(c.status));
const ROTULO_HIST: Record<string, string> = {
  atendimento_encerrado: 'encerrado', atendimento_reaberto: 'reaberto', atendimento_cancelado: 'cancelado',
};
</script>

<style scoped>
.cancelar-sol { margin-top: .6rem; } .cancelar-sol summary { cursor: pointer; color: var(--vermelho, #b3261e); font-weight: 600; font-size: .9rem; }
.bloco-sec { border-bottom: 1px solid #eef1f5; padding-bottom: .7rem; margin-bottom: .7rem; }
.horarios { margin-top: .8rem; } .horarios summary { cursor: pointer; font-weight: 600; }
.cartao-sala { border-left: 6px solid var(--azul, #0c3a67); }
.botao-grande { font-size: 1.15rem; padding: .85rem 1.6rem; }
.passos-sala { list-style: none; padding: 0; margin: 1rem 0 .4rem; display: grid; grid-template-columns: repeat(6, 1fr); position: relative; }
.passos-sala::before { content: ''; position: absolute; top: .85rem; left: 8%; right: 8%; height: 3px; background: #e3e7ed; }
.passos-sala li { display: flex; flex-direction: column; align-items: center; text-align: center; gap: .2rem; position: relative; z-index: 1; }
.passos-sala .bola { width: 1.75rem; height: 1.75rem; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: .8rem;
  background: #fff; border: 2px solid #cfd6df; color: #8a94a3; }
.passos-sala li.feito .bola { background: #1e9e5a; border-color: #1e9e5a; color: #fff; }
.passos-sala li.agora .bola { border-color: #1f6fc4; color: #1f6fc4; box-shadow: 0 0 0 4px rgba(31,111,196,.2); }
.passos-sala li.pulado .bola { border-style: dashed; }
.passos-sala .rot { font-size: .78rem; font-weight: 600; line-height: 1.15; }
.passos-sala .hora { font-size: .74rem; opacity: .75; min-height: 1rem; }
.proxima-acao { border: 1px solid var(--borda, #d9dee5); border-radius: 12px; padding: .9rem 1rem; margin-top: .8rem; }
.pa-titulo { font-weight: 700; margin-bottom: .5rem; }
.pa-etapas { list-style: none; padding: 0; margin: 0 0 .8rem; display: grid; grid-template-columns: repeat(3, 1fr); gap: .3rem;
  background: #f2f5f9; border-radius: 999px; padding: .25rem; }
.pa-etapas li { text-align: center; padding: .45rem .3rem; border-radius: 999px; font-weight: 600; color: #8a94a3;
  display: flex; align-items: center; justify-content: center; gap: .35rem; }
.pa-etapas li.agora { background: #fff; color: var(--azul, #0c3a67); box-shadow: 0 1px 3px rgba(12,58,103,.15); }
.pa-etapas li.feito { color: #1e7a45; }
.pa-bola { display: inline-grid; place-items: center; width: 1.3rem; height: 1.3rem; border-radius: 50%; font-size: .72rem;
  border: 2px solid currentColor; }
.pa-corpo h3 { margin: 0 0 .3rem; font-size: 1.05rem; }
.pa-corpo p { margin: 0 0 .6rem; }
.outras-acoes { margin-top: .8rem; }
.outras-acoes > summary { cursor: pointer; font-weight: 600; color: var(--azul, #0c3a67); }
.proximo-passo { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; background: #f3f7fc; border-radius: 10px; padding: .7rem .9rem; margin-top: .6rem; }
.chamados { margin-top: 1rem; border-top: 1px solid #eef1f5; padding-top: .8rem; }
.chamados h3 { margin: 0 0 .5rem; font-size: 1rem; }
.linha-chamados { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: .7rem; }
.form-chamado { display: flex; flex-direction: column; gap: .4rem; border: 1px solid var(--borda, #d9dee5); border-radius: 10px; padding: .7rem; margin: 0; }
.cab-chamado .ic, .lista-chamados .ic { font-size: 1.4rem; }
.lista-chamados { list-style: none; padding: 0; margin: .7rem 0 0; display: flex; flex-direction: column; gap: .4rem; }
.lista-chamados li { display: flex; gap: .7rem; align-items: center; padding: .55rem .8rem; border-radius: 10px; border: 1px solid #e3e7ed; }
.ch-aberto { background: #fff4e5; border-color: #f0c37a !important; }
.ch-direcionado { background: #eaf3ff; border-color: #a9c8f0 !important; }
.ch-atendido { background: #eef9f2; opacity: .8; }
.ch-cancelado { opacity: .55; }
@media (max-width: 640px) { .passos-sala .rot { font-size: .62rem; } }
</style>
