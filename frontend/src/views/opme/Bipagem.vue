<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>{{ op.titulo }}</h1>
        <p v-if="operacao !== 'dispensar_sala'">{{ op.ajuda }}</p>
        <p v-if="at"><strong>{{ d.descricao_atendimento }}</strong></p>
      </div>
      <div class="acoes">
        <a v-if="operacao === 'devolver_fornecedor'" class="botao secundario" data-sem-foco="1"
           href="/almoxarifado/romaneios-fornecedor">Romaneio (PDF com assinaturas)</a>
        <template v-if="at">
          <a v-if="operacao === 'registrar_uso' && at.status === 'aberto' && !at.uso_finalizado_em" class="botao" data-sem-foco="1"
             :href="`/sala-procedimento/atendimento/${at.id_atendimento}/concluir`">Finalizar registro de uso e devoluções</a>
          <a v-if="operacao !== 'dispensar_sala'" class="botao secundario" data-sem-foco="1"
             :href="`/${op.modulo}/atendimento/${at.id_atendimento}`">Ver atendimento</a>
          <a v-if="operacao === 'registrar_uso' && at.status === 'aberto' && !at.uso_finalizado_em && resumo && !resumo.utilizados"
             class="botao secundario" data-sem-foco="1" :href="`/sala-procedimento/atendimento/${at.id_atendimento}#cancelar`">Procedimento cancelado</a>
        </template>
        <template v-if="operacao === 'dispensar_sala'">
          <form v-if="at" method="post" :action="`/farmacia/atendimento/${at.id_atendimento}/finalizar-dispensa`" style="display:inline">
            <button class="botao" data-sem-foco="1">Finalizar dispensa</button></form>
          <a v-if="at && at.status === 'aberto' && resumo && !resumo.utilizados" class="botao secundario" data-sem-foco="1" href="#cancelar">Procedimento cancelado</a>
          <a class="botao secundario" data-sem-foco="1" href="/farmacia/atendimentos">Outro paciente</a>
        </template>
        <a v-else class="botao secundario" data-sem-foco="1" :href="`/${op.modulo}`">Voltar</a>
      </div>
    </div>

    <template v-if="operacao === 'dispensar_sala' && at && at.status === 'aberto' && resumo && !resumo.utilizados">
      <details v-if="resumo.na_sala" class="cartao" id="cancelar" style="margin-top:1rem" :hidden="route.hash !== '#cancelar'" :open="route.hash === '#cancelar'">
        <summary style="cursor:pointer"><strong>Procedimento cancelado?</strong></summary>
        <p class="pequeno" style="margin-top:.6rem">A sala já confirmou o recebimento de {{ resumo.na_sala }} item(ns)
          deste paciente. Nesse caso o cancelamento é feito pela <strong>sala de procedimento</strong>
          (na ficha do atendimento) — o material volta direto para a farmácia do mesmo jeito.</p>
      </details>
      <CancelarProcedimento v-else :acao="`/farmacia/atendimento/${at.id_atendimento}/cancelar`"
                            :dispensados="resumo.transito_sala" :voltar="`/bipagem/dispensar_sala?atendimento=${at.id_atendimento}`"
                            :oculto="true" :motivos="d.motivos_cancelamento" />
    </template>

    <div v-if="resumo && !['dispensar_sala', 'registrar_uso'].includes(operacao)" class="trilha">
      <div class="etapa destaque"><strong>{{ resumo.utilizados }}</strong> utilizados neste paciente</div>
    </div>

    <div id="tela-bipagem" class="bipagem">
      <div>
        <div class="caixa-scanner">
          <div v-if="op.define_farmacia" class="campo" style="margin-bottom:1rem">
            <label class="obrigatorio" for="farmacia-destino">Farmácia de destino</label>
            <select id="farmacia-destino" v-model="farmaciaDestino" data-sem-foco="1">
              <option v-for="(rotulo, chave) in d.farmacias" :key="chave" :value="chave">{{ rotulo }}</option>
            </select>
            <div class="dica">
              Os estoques das duas farmácias são separados. Confira o destino antes de
              começar a bipar — todos os itens desta sessão vão para a farmácia escolhida.
            </div>
          </div>
          <div v-else-if="op.escopo_farmacia" :class="['aviso', d.farmacia_do_paciente ? 'erro' : '']" style="margin-bottom:1rem">
            Trabalhando na <strong>{{ d.farmacias[d.farmacia] }}</strong>.
            <a href="/farmacia">trocar de farmácia</a>
            <template v-if="d.farmacia_do_paciente"><br><strong>Atenção:</strong> este paciente é atendido pela
              <strong>{{ d.farmacias[d.farmacia_do_paciente] }}</strong>. Só sai material do estoque da farmácia em que você está.</template>
          </div>

          <template v-if="op.confirmacao_papel">
            <!-- A confirmação vem ANTES da leitura de propósito: o campo do leitor
                 fica bloqueado até a entrega ser aberta. -->
            <div v-if="!entrega" class="aviso info" id="entrega-fechada" style="margin-bottom:1rem">
              <strong>Confirmação de quem recebe.</strong> {{ op.confirmacao_aviso }}
              <template v-if="d.confirmadores?.length">
                <div class="campo" style="margin-top:.6rem">
                  <label class="obrigatorio" for="usuario-responsavel">Quem está recebendo</label>
                  <select id="usuario-responsavel" v-model="usuarioResponsavel" data-sem-foco="1">
                    <option value="">— escolha o {{ op.confirmacao_quem }} —</option>
                    <option v-for="c in d.confirmadores" :key="c.username" :value="c.username">{{ c.nome }}<template v-if="c.setor"> · {{ c.setor }}</template></option>
                  </select>
                </div>
                <div class="campo">
                  <label class="obrigatorio" for="senha-responsavel">Senha de quem está recebendo</label>
                  <input type="password" id="senha-responsavel" v-model="senhaResponsavel" data-sem-foco="1" autocomplete="off"
                         placeholder="digitada pela própria pessoa, aqui">
                </div>
                <button type="button" class="botao" id="abrir-entrega" data-sem-foco="1" :disabled="abrindoEntrega" @click="abrirEntrega">
                  {{ operacao === 'devolver_nao_utilizado' ? 'Abrir devolução' : 'Abrir entrega' }}
                </button>
                <div class="dica" style="margin-top:.5rem">
                  A senha é digitada uma vez e vale para os materiais desta {{ operacao === 'devolver_nao_utilizado' ? 'devolução' : 'entrega' }}.
                  A entrega fica aberta na tela, com o nome de quem confirmou, e se encerra sozinha depois de alguns minutos parada.
                </div>
              </template>
              <div v-else class="dica" style="margin-top:.6rem">
                Nenhum usuário ativo com o papel de {{ op.confirmacao_quem }} está cadastrado — sem isso não há quem
                confirme o recebimento. Fale com a administração antes de continuar.
              </div>
            </div>
            <div v-else class="aviso sucesso" id="entrega-aberta" style="margin-bottom:1rem">
              <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
                <div style="flex:1 1 auto;min-width:14rem">
                  <strong>Entrega aberta.</strong> Conferida por <b>{{ entrega.nome }}</b> — <span>{{ textoContagemEntrega }}</span>.
                </div>
                <button type="button" class="botao secundario pequeno" data-sem-foco="1" @click="encerrarEntrega()">Encerrar entrega</button>
              </div>
            </div>
          </template>

          <div v-if="operacao === 'dispensar_sala'" class="aviso" style="margin-bottom:.8rem">
            Bipe cada OPME separado para este paciente. <strong>Caixa de consignado?</strong>
            Bipe o código da CAIXA — vai inteira.
          </div>
          <div v-if="operacao === 'registrar_uso' && d.trava_sala?.length" class="aviso erro" style="margin-bottom:1rem;border:3px solid var(--vermelho, #b3261e)">
            <strong>BIPAGEM BLOQUEADA neste prontuário.</strong> A farmácia dispensou material para este
            paciente e o recebimento ainda não foi confirmado. Confira os materiais e confirme o recebimento com seu usuário; depois bipe:
            <ul class="lista" style="margin:.4rem 0 0 1.1rem">
              <li v-for="t in d.trava_sala" :key="t.id_dispensacao">Prontuário <strong>{{ t.prontuario }}</strong><template v-if="t.paciente"> · {{ t.paciente }}</template>
                — {{ t.qtd }} item(ns) ·
                <a :href="`/dispensacoes/${t.id_dispensacao}`" data-sem-foco="1"><strong>confirmar recebimento</strong></a>
                ou, se o procedimento não vai acontecer,
                <a :href="`/sala-procedimento/atendimento/${t.id_atendimento}#cancelar`" data-sem-foco="1"><strong>procedimento cancelado</strong></a>
                (o material volta para a farmácia)</li>
            </ul>
          </div>
          <div v-if="operacao === 'registrar_uso' && d.complemento_pendente?.length" class="aviso info" style="margin-bottom:1rem">
            <strong>A farmácia dispensou mais {{ d.complemento_pendente.length }} item(ns) para este paciente.</strong>
            Pode bipar normalmente — a ciência desses itens é dada ao <strong>finalizar os materiais utilizados</strong>.
          </div>
          <!-- v18.18: finalizar não trava mais a sala. Continua bipando até a farmácia concluir. -->
          <div v-if="operacao === 'registrar_uso' && at && at.uso_finalizado_em" class="aviso info" style="margin-bottom:1rem">
            <strong>Materiais utilizados já finalizados</strong> em {{ f.dataHoraBr(at.uso_finalizado_em) }}.
            Se precisar, continue bipando normalmente — inclusive material que chegou depois. A sala só fecha
            quando a farmácia concluir a conferência.
            <template v-if="d.complemento_pendente?.length">
              <br><a class="botao pequeno" style="margin-top:.5rem" data-sem-foco="1"
                     :href="`/sala-procedimento/atendimento/${at.id_atendimento}/concluir`">
                Dar ciência dos {{ d.complemento_pendente.length }} item(ns) que chegaram depois</a>
            </template>
          </div>
          <template v-if="operacao === 'registrar_uso'">
            <div v-if="!caixaAtiva" class="pequeno suave" id="caixa-ativa-vazia" style="margin-bottom:.6rem">
              Bipe só o item — mesmo o que está em caixa de consignado.
            </div>
            <div v-else class="caixa-ativa" id="caixa-ativa">
              <div class="caixa-ativa-texto">
                <span class="caixa-ativa-rotulo">CAIXA ATIVA</span>
                <strong class="mono">{{ caixaAtiva.id_caixa }}</strong>
                <span> {{ caixaAtiva.nome }}<template v-if="caixaAtiva.fornecedor"> · {{ caixaAtiva.fornecedor }}</template></span>
                <div class="pequeno">Os itens bipados agora saem desta caixa. Terminou? Clique em “Sair da caixa” ou bipe outra caixa.</div>
              </div>
              <button type="button" class="botao secundario pequeno" id="sair-caixa" data-sem-foco="1" @click="sairDaCaixa">Sair da caixa</button>
            </div>
          </template>

          <!-- v18.10: sala fechada — abre aqui mesmo, sem sair da tela -->
          <div v-if="salaFechada" id="sala-fechada" class="cartao"
               style="margin:0 0 1rem;padding:1rem 1.2rem;border:3px solid var(--vermelho, #b3261e);background:#fdecea">
            <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap">
              <div style="flex:1 1 280px">
                <strong style="font-size:1.25rem;color:var(--vermelho, #b3261e)">A sala ainda não foi aberta</strong>
                <div>Abra a sala para liberar o registro de uso deste paciente.</div>
              </div>
              <button type="button" class="botao" data-sem-foco="1" style="font-size:1.1rem;padding:.7rem 1.4rem"
                      :disabled="abrindoSala" @click="abrirSalaAgora">{{ abrindoSala ? 'Abrindo…' : '▶ Abrir sala agora' }}</button>
            </div>
            <p v-if="erroAbrirSala" class="aviso erro pequeno" style="margin:.6rem 0 0">{{ erroAbrirSala }}</p>
          </div>

          <!-- v18: problema com o material (caiu, danificado) — marca o PRÓXIMO bip -->
          <div v-if="operacao === 'registrar_uso' && uso" class="cartao" id="avaria-proximo"
               :style="`margin:0 0 1rem;padding:.8rem 1rem;${avariaProx ? 'border:2px solid var(--vermelho, #b3261e);background:#fdecea' : 'background:#fbf2e2;border-left:5px solid #b7791f'}`">
            <div style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap">
              <strong class="pequeno">⚠ O material caiu ou veio com problema?</strong>
              <span class="pequeno suave">Escolha antes de bipar — o próximo item sai marcado:</span>
            </div>
            <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.5rem">
              <button v-for="m in (uso.motivos_avaria || [])" :key="m" type="button" data-sem-foco="1"
                      :class="['botao', 'pequeno', avariaProx === m ? 'perigo' : 'secundario']"
                      @click="avariaProx = avariaProx === m ? '' : m">{{ m }}</button>
            </div>
            <div v-if="avariaProx" style="display:flex;gap:.4rem;align-items:center;flex-wrap:wrap;margin-top:.5rem">
              <input type="text" v-model="avariaDetalhe" data-sem-foco="1" style="flex:1 1 260px"
                     :placeholder="avariaProx === 'Outro problema' ? 'descreva o problema (obrigatório)' : 'detalhe (opcional)'">
              <span class="pequeno"><strong>Agora bipe o material.</strong></span>
              <button type="button" class="botao secundario pequeno" data-sem-foco="1" @click="avariaProx = ''; avariaDetalhe = ''">cancelar</button>
            </div>
          </div>

          <label for="codigo">Bipe o código de barras</label>
          <input type="text" id="codigo" ref="campo" v-model="codigo" autocomplete="off" autocapitalize="off"
                 spellcheck="false" inputmode="text" :disabled="campoTravado"
                 :placeholder="op.confirmacao_papel && !entrega ? 'confirme a entrega acima para liberar a leitura' : salaFechada ? 'abra a sala acima para liberar a leitura' : 'aguardando leitura…'"
                 @keydown.enter.prevent="lerCampo" @input="conf?.fecharSeVerde()">
          <template v-if="d.motivos_selecao_manual?.length">
            <div class="pequeno" style="margin-top:.45rem">
              <button type="button" id="abrir-selecao-manual" data-sem-foco="1" @click="abrirManual"
                      style="background:none;border:0;padding:0;color:var(--azul, #0c3a67);text-decoration:underline;cursor:pointer;font:inherit">
                Não consegue bipar? Selecionar pelo código AGHU ou nome</button>
              <span class="suave"> — só em caso excepcional; fica registrado com o motivo.</span>
            </div>
            <div v-if="operacao === 'registrar_uso' && at && at.status === 'aberto'" class="pequeno" style="margin-top:.3rem">
              <a :href="`/sala-procedimento/atendimento/${at.id_atendimento}/nao-cadastrado`" data-sem-foco="1"
                 style="color:var(--vermelho, #b3261e)">Material não cadastrado no sistema?</a>
              <span class="suave"> — registre lote e validade; o almoxarifado regulariza.</span>
            </div>
          </template>
          <div v-if="naoRegistrado" id="ultimo-nao-registrado" class="pequeno" style="margin-top:.4rem;color:var(--vermelho, #b3261e);font-weight:600">
            Última leitura NÃO registrada: {{ naoRegistrado }}
          </div>
          <div class="pequeno suave" style="margin-top:.4rem">
            O campo fica sempre ativo. Pode bipar um item atrás do outro sem clicar em nada.
            Também aceita o número de série ou o ID da unidade digitado.
          </div>

          <!-- v18: devoluções ao fornecedor abertas (cada item entra na do fornecedor dele) -->
          <div v-if="operacao === 'devolver_fornecedor'" class="cartao" id="devolucoes-abertas"
               style="margin:1rem 0 0;padding:.8rem 1rem;border-left:5px solid #b7791f;background:#fbf2e2">
            <strong>Devoluções abertas</strong>
            <span class="pequeno suave"> — cada item bipado entra na devolução do fornecedor dele. Ao terminar, finalize e baixe o romaneio.</span>
            <p v-if="!devAbertas.length" class="pequeno suave" style="margin:.4rem 0 0">Nenhuma aberta. Bipe o primeiro item para abrir uma devolução.</p>
            <div v-for="dv in devAbertas" :key="dv.id_devolucao"
                 style="display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin-top:.5rem;padding-top:.5rem;border-top:1px solid #f0dcb8">
              <span class="mono"><strong>{{ dv.id_devolucao }}</strong></span>
              <span style="flex:1 1 200px">{{ dv.fornecedor }} · {{ dv.qtd_itens }} item(ns)</span>
              <a class="botao secundario pequeno" data-sem-foco="1" :href="`/almoxarifado/devolucao-fornecedor/${dv.id_devolucao}`">abrir</a>
              <form method="post" :action="`/almoxarifado/devolucao-fornecedor/${dv.id_devolucao}/finalizar`" style="margin:0"
                    :data-confirmar="`Finalizar a devolução ${dv.id_devolucao} (${dv.qtd_itens} item(ns) para ${dv.fornecedor})?`">
                <button class="botao pequeno" data-sem-foco="1" :disabled="!dv.qtd_itens">finalizar</button>
              </form>
            </div>
          </div>

          <!-- Registro de uso: lista do que já foi registrado no paciente -->
          <div v-if="operacao === 'registrar_uso' && uso" class="aviso sucesso" id="uso-registrado" style="margin-top:1rem">
            <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
              <div style="flex:1 1 auto">
                <strong>Já registrado como utilizado neste paciente:</strong>
                <span id="uso-contagem"> {{ uso.lista.length }} item(ns)</span>
                <span class="pequeno suave"> — o último bipado fica em cima.</span>
              </div>
            </div>
            <datalist id="motivos-excluir-uso">
              <option v-for="m in d.motivos_excluir_uso" :key="m" :value="m"></option>
            </datalist>
            <table style="margin-top:.6rem">
              <tbody id="uso-lista">
                <tr v-for="i in uso.lista" :key="i.id_unidade" :class="{ 'novo-na-lista': i.id_unidade === ultimoUso }">
                  <td class="pequeno"><span class="mono"><strong>AGHU {{ i.aghu || '—' }}</strong></span> · {{ i.produto }}<br>
                    <span class="mono suave">lote {{ i.lote || '—' }} · val. {{ i.validade || '—' }}</span>
                    <span v-if="i.caixa" class="etiqueta cinza"> caixa {{ i.caixa }}</span>
                    <template v-if="i.avaria"><br><span class="etiqueta vermelho">⚠ {{ i.avaria.motivo }}</span>
                      <span v-if="i.avaria.detalhe" class="suave"> {{ i.avaria.detalhe }}</span></template>
                    <div v-if="sinalizando === i.id_unidade" style="display:flex;gap:.3rem;flex-wrap:wrap;margin-top:.4rem">
                      <select v-model="sinalMotivo" data-sem-foco="1" style="width:auto">
                        <option value="">— problema —</option>
                        <option v-for="m in (uso.motivos_avaria || [])" :key="m" :value="m">{{ m }}</option>
                      </select>
                      <input type="text" v-model="sinalDetalhe" data-sem-foco="1" placeholder="detalhe" style="width:12rem"
                             @keydown.enter.prevent="enviarSinal(i.id_unidade)">
                      <button type="button" class="botao perigo pequeno" data-sem-foco="1" :disabled="!sinalMotivo" @click="enviarSinal(i.id_unidade)">salvar</button>
                      <button type="button" class="botao secundario pequeno" data-sem-foco="1" @click="sinalizando = ''">voltar</button>
                    </div></td>
                  <td class="pequeno suave">{{ i.quando }} · {{ i.por }}</td>
                  <td style="text-align:right">
                    <button v-if="uso.pode_sinalizar && sinalizando !== i.id_unidade && excluindo !== i.id_unidade" type="button"
                            class="botao secundario pequeno" data-sem-foco="1" style="margin:0 .3rem .3rem 0"
                            @click="sinalizando = i.id_unidade; sinalMotivo = i.avaria?.motivo || ''; sinalDetalhe = i.avaria?.detalhe || ''">
                      {{ i.avaria ? 'alterar problema' : '⚠ sinalizar problema' }}</button>
                    <template v-if="uso.pode_excluir">
                      <div v-if="excluindo === i.id_unidade" style="display:flex;gap:.3rem;justify-content:flex-end;flex-wrap:wrap">
                        <input type="text" list="motivos-excluir-uso" data-sem-foco="1" v-model="motivoExclusao" ref="campoMotivoExclusao"
                               placeholder="motivo da exclusão" style="width:13rem" @keydown.enter.prevent="confirmarExclusao(i.id_unidade)">
                        <button type="button" class="botao perigo pequeno" data-sem-foco="1" :disabled="enviandoExclusao" @click="confirmarExclusao(i.id_unidade)">confirmar</button>
                        <button type="button" class="botao secundario pequeno" data-sem-foco="1" @click="cancelarExclusao">voltar</button>
                      </div>
                      <button v-else type="button" class="botao secundario pequeno" data-sem-foco="1" @click="iniciarExclusao(i.id_unidade)">excluir</button>
                    </template>
                  </td>
                </tr>
                <tr v-if="!uso.lista.length" class="uso-vazio"><td class="pequeno suave" colspan="3">Nenhum material registrado ainda.</td></tr>
              </tbody>
            </table>
          </div>

          <template v-if="operacao === 'dispensar_sala' && at">
            <div class="cartao" id="painel-solicitacao" style="margin:1rem 0 0;padding:.9rem;border-left:5px solid var(--azul, #0c3a67)">
              <SolicitacaoPainel :sol="solicitacao" modo="farmacia" :atendimento="at" :motivos-outro-codigo="d.motivos_outro_codigo" :motivos-falta="d.motivos_falta" />
            </div>
            <details v-if="solicitacao?.existe" class="cartao" id="finalizar" style="margin:1rem 0 0;border-left:5px solid var(--amarelo, #b26a00)"
                     :open="route.hash === '#finalizar'">
              <summary style="cursor:pointer"><strong>Finalizar a dispensa com item faltando</strong>
                <span class="pequeno suave"> — o motivo é obrigatório e a sala vê o que não veio</span></summary>
              <form method="post" :action="`/farmacia/atendimento/${at.id_atendimento}/finalizar-dispensa`" style="margin-top:.7rem">
                <div class="campo"><label class="obrigatorio">Motivo</label>
                  <input type="text" name="motivo" list="motivos-faltas" data-sem-foco="1" placeholder="Ex.: sem estoque na farmácia">
                  <datalist id="motivos-faltas"><option value="Sem estoque na farmácia"></option><option value="Material substituído por similar (combinado com a sala)"></option><option value="Sala desistiu do item"></option><option value="Aguardando reposição do fornecedor"></option></datalist></div>
                <button class="botao" data-sem-foco="1">Finalizar dispensa assim mesmo</button>
              </form>
            </details>
          </template>

          <!-- Dispensação: o que já saiu da farmácia para este paciente (aguardando a sala) -->
          <div v-if="operacao === 'dispensar_sala' && pendenteLista.length" class="aviso info" id="devolucao-pendente" style="margin-top:1rem">
            <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
              <div style="flex:1 1 auto">
                <strong>Saiu da farmácia — aguardando a confirmação da sala:</strong>
                <span id="devolucao-contagem"> {{ contagemPendente }}</span>
              </div>
              <a v-if="at" class="botao secundario pequeno" data-sem-foco="1" data-baixar
                 :href="`/dispensacoes/atendimento/${at.id_atendimento}/pdf`">Baixar PDF</a>
            </div>
            <table style="margin-top:.6rem">
              <tbody id="pendente-lista">
                <tr v-for="(i, n) in pendenteAgrupado" :key="i.remover || n" :class="{ 'novo-na-lista': i.novo }">
                  <td class="pequeno">
                    <template v-if="i.tipo === 'caixa'"><strong>Caixa {{ i.id_caixa }}</strong> — {{ i.quantidade }} item(ns)</template>
                    <template v-else>
                      <span class="mono"><strong>AGHU {{ i.aghu || '—' }}</strong></span> · {{ i.descricao }}<br>
                      <span class="mono suave">lote {{ i.lote || '—' }} · val. {{ i.validade || '—' }}</span>
                      <span v-if="i.id_caixa" class="etiqueta cinza"> caixa {{ i.id_caixa }}</span>
                    </template>
                  </td>
                  <td class="pequeno suave">{{ i.quando }} · {{ i.por }}</td>
                  <td style="text-align:right">
                    <form method="post" :action="i.remover" style="display:inline">
                      <button class="botao secundario pequeno" data-sem-foco="1">{{ i.id_caixa ? 'tirar a caixa' : 'tirar' }}</button>
                    </form>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="d.exige_motivo" class="campo" style="margin-top:1rem">
            <label class="obrigatorio" for="motivo">
              <template v-if="d.destinos_outros?.length">Destino — setor / procedimento (aplicado a todas as leituras)</template>
              <template v-else>Motivo (aplicado a todas as leituras)</template>
            </label>
            <input type="text" id="motivo" v-model="motivo" data-sem-foco="1" list="destinos-outros"
                   :placeholder="d.destinos_outros?.length ? 'Ex.: Ambulatório — curativo complexo' : 'Ex.: embalagem violada'">
            <datalist v-if="d.destinos_outros?.length" id="destinos-outros">
              <option v-for="x in d.destinos_outros" :key="x" :value="x"></option>
            </datalist>
            <p v-if="d.destinos_outros?.length" class="pequeno suave" style="margin:.3rem 0 0">
              Em “Observação”, registre quem está levando o material (nome/setor). O item sai do estoque agora e o
              uso não é acompanhado item a item por aqui.</p>
          </div>
          <details id="extras" :open="extrasAbertos" style="margin-top:1rem" @toggle="extrasAbertos = ($event.target as HTMLDetailsElement).open">
            <summary class="pequeno" style="cursor:pointer">
              <template v-if="d.motivo_opcional">Justificativa / observação</template><template v-else>Observação</template>
              <span class="suave"> (se precisar)</span></summary>
            <div v-if="d.motivo_opcional" class="campo" style="margin-top:.6rem">
              <label for="motivo">Justificativa <span class="opcional">(só é exigida em caso excepcional)</span></label>
              <input type="text" id="motivo" ref="campoMotivo" v-model="motivo" data-sem-foco="1" placeholder="preencha se o sistema pedir">
              <div class="dica">
                Se um material vencido ou de lote bloqueado chegar a ser usado, o registro é
                aceito — não registrar seria pior —, mas exige justificativa e é sinalizado à gestão.
              </div>
            </div>
            <div class="campo" style="margin-top:.75rem">
              <label for="observacao">Observação <span class="opcional">(opcional)</span></label>
              <input type="text" id="observacao" v-model="observacao" data-sem-foco="1" placeholder="Fica registrada em cada leitura">
            </div>
          </details>

          <div v-if="!['dispensar_sala', 'registrar_uso'].includes(operacao)" class="contador-grande">
            <div><div class="numero" id="contador-lidos">{{ lidos }}</div><div class="rotulo">lidos agora</div></div>
            <div v-if="op.mostra_pendentes"><div class="numero" id="contador-pendentes">{{ contadorPendentes }}</div><div class="rotulo">ainda pendentes</div></div>
          </div>

          <!-- Conferência da caixa (revisão por produto e lote, sem bipar item a item) -->
          <div v-if="revisao" id="resultado">
            <div class="resultado-linha" style="background:var(--azul-claro);display:block">
              <div class="titulo">Confira a caixa {{ revisao.rev.id_caixa }} · {{ revisao.rev.nome }}</div>
              <div class="detalhe">{{ revisao.rev.devolucao
                ? 'Conte o que voltou, por produto — sem bipar item a item. Se faltar algo, diga quantos não estão: esses continuam como pendência da sala, e a sala é avisada.'
                : 'Confira o que vai, por produto. Se algo não deve ir, diga quantos ficam: esses saem da caixa e voltam ao estoque da farmácia.' }}</div>
              <div class="tabela-rolagem" style="margin-top:.6rem">
                <table class="tabela-detalhe">
                  <thead><tr><th>AGHU</th><th>Produto</th><th class="num">Deve ter</th><th class="num">{{ revisao.rev.rotulo_fora }}</th></tr></thead>
                  <tbody>
                    <tr v-for="(g, n) in revisao.rev.grupos" :key="n">
                      <td class="mono pequeno">{{ g.aghu }}</td>
                      <td>{{ g.produto }}
                        <div class="pequeno suave">lote {{ g.lote }}<template v-if="g.serie"> · série {{ g.serie }}</template> · val. {{ g.validade }}</div></td>
                      <td class="num"><strong>{{ g.quantidade }}</strong></td>
                      <td class="num"><input type="number" min="0" :max="g.quantidade" v-model.number="revisao.fora[n]" data-sem-foco="1"
                                             inputmode="numeric" style="width:4.5rem;text-align:center" @input="limitarFora(n)"></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-if="revisao.avisar" class="aviso alerta" style="margin-top:.6rem">
                Conclua esta conferência (confirmar ou cancelar) antes de bipar outro código.
              </div>
              <div class="linha-botoes" style="margin-top:.7rem">
                <button type="button" class="botao" data-sem-foco="1" :disabled="revisaoVai <= 0" @click="confirmarRevisao">{{ textoConfirmarRevisao }}</button>
                <button type="button" class="botao secundario" data-sem-foco="1" @click="cancelarRevisao">Cancelar</button>
              </div>
            </div>
          </div>
          <ResultadoLeitura v-else ref="resultado">
            <div v-if="mostrarProntoParaLer" class="resultado-linha" style="background:var(--cinza-claro)">
              <div class="icone">⌖</div>
              <div><div class="titulo">Pronto para ler</div>
                   <div class="detalhe">O resultado de cada leitura aparece aqui.</div></div>
            </div>
          </ResultadoLeitura>

          <div class="linha-botoes">
            <button type="button" class="botao secundario" id="btn-confirmar" data-sem-foco="1" @click="lerCampo">Confirmar código digitado</button>
            <label class="pequeno" style="display:flex;align-items:center;gap:.4rem;font-weight:400">
              <input type="checkbox" id="som" v-model="som" data-sem-foco="1" style="width:auto"> som de confirmação
            </label>
          </div>
        </div>

        <div v-if="!((operacao === 'registrar_uso' && uso) || (operacao === 'dispensar_sala' && at))" class="cartao" style="margin-top:1rem">
          <h2>Lidos nesta sessão</h2>
          <ul class="lista-bipados" id="lista-bipados">
            <li v-for="l in listaLidos" :key="l.chave">
              <span :class="['etiqueta', l.caixa ? 'roxo' : 'verde']">{{ l.n }}</span>
              <span class="produto">
                <template v-if="l.caixa">
                  <strong><span class="mono">{{ l.caixa.id_caixa }}</span> {{ l.caixa.nome }}</strong>
                  <span>Caixa com {{ l.caixa.total }} item(ns)<template v-if="l.caixa.ciclo"> · ciclo {{ l.caixa.ciclo }}</template></span>
                </template>
                <template v-else>
                  <strong :title="l.item.produto"><span class="mono">{{ l.item.aghu }}</span> {{ l.item.produto }}</strong>
                  <span>Lote {{ l.item.lote }} · val. {{ l.item.validade }} · {{ l.item.id_unidade }}</span>
                </template>
              </span>
              <button v-if="!l.caixa" type="button" class="botao secundario pequeno" data-sem-foco="1" @click="desfazer(l.item.id_unidade)">Desfazer</button>
            </li>
          </ul>
          <p v-if="!listaLidos.length" class="vazio">Nenhuma leitura ainda.</p>
        </div>
      </div>

      <aside>
        <div v-if="d.caixas_pendentes?.length" class="cartao" style="border-left:5px solid var(--roxo);margin-bottom:1rem">
          <h2>{{ d.caixas_pendentes.length }} caixa(s) nesta etapa</h2>
          <p class="suave pequeno">Bipe o código da caixa e tudo que está dentro se move de uma vez.</p>
          <div v-for="c in d.caixas_pendentes" :key="c.id_caixa" style="padding:.5rem 0;border-bottom:1px solid var(--borda)">
            <strong class="mono">{{ c.id_caixa }}</strong>
            <span class="suave pequeno"> {{ c.especialidade }}</span><br>
            <span class="pequeno">{{ c.nome }}</span><br>
            <span class="suave pequeno">{{ c.total }} item(ns) dentro</span>
          </div>
        </div>

        <div v-if="!op.mostra_pendentes" class="cartao">
          <h2>Consultar antes de bipar</h2>
          <p class="suave pequeno">
            <template v-if="operacao === 'devolver_nao_utilizado'">Aqui entra só material que não foi registrado como utilizado. Há</template>
            <template v-else>Esta operação retira do estoque, então não há lista de pendências — há</template>
            <strong> {{ d.elegiveis }}</strong> item(ns) disponíveis no {{ operacao === 'dispensar_sala' ? 'estoque da farmácia' : 'estoque' }}.
            Use a busca só se precisar conferir se algo está disponível.
          </p>
          <form method="get" :action="`/bipagem/${operacao}`">
            <input v-if="at" type="hidden" name="atendimento" :value="at.id_atendimento">
            <div class="campo">
              <label>Código AGHU, descrição, lote ou código de barras</label>
              <input type="text" name="busca" :defaultValue="d.busca" data-sem-foco="1" placeholder="ex.: AGHU-101 ou parafuso">
            </div>
            <button class="botao secundario pequeno" data-sem-foco="1">Buscar</button>
          </form>
          <div v-if="d.busca" class="pendentes-lista" style="margin-top:.9rem">
            <div v-for="(item, n) in d.resultados" :key="n" style="padding:.5rem 0;border-bottom:1px solid var(--borda)">
              <strong class="mono">{{ item.aghu }}</strong>
              <span class="pequeno"> {{ item.produto }}</span><br>
              <span class="suave pequeno">
                Lote {{ item.lote }} · val. {{ item.validade }}<template v-if="item.iguais > 1"> · {{ item.iguais }} unidades iguais</template>
              </span>
            </div>
            <p v-if="!d.resultados?.length" class="vazio">Nada encontrado para “{{ d.busca }}” nesta situação.</p>
          </div>
        </div>
        <div v-else class="cartao">
          <h2>Ainda pendente</h2>
          <p class="suave pequeno">{{ op.exige_atendimento ? 'Materiais deste atendimento que ainda não passaram por esta etapa.' : 'Materiais que foram enviados e aguardam a sua conferência.' }}</p>
          <form v-if="pendentes.length" method="post" :action="`/bipagem/${operacao}/pendencias`" data-confirmar="Confirmar o tratamento dos itens marcados?">
            <input type="hidden" name="atendimento" :value="at ? at.id_atendimento : ''">
            <div class="pendentes-lista" id="pendentes">
              <label class="pequeno" style="font-weight:400;display:flex;gap:.4rem;align-items:center;padding:.3rem 0">
                <input type="checkbox" data-sem-foco="1" style="width:auto" @change="marcarTodosPendentes"> marcar todos
              </label>
              <label v-for="item in pendentes" :key="item.id_unidade"
                     style="display:flex;gap:.5rem;align-items:flex-start;padding:.5rem 0;border-bottom:1px solid var(--borda);font-weight:400">
                <input type="checkbox" name="ids" :value="item.id_unidade" v-model="pendentesMarcados" data-sem-foco="1" style="width:auto;margin-top:.25rem">
                <span style="flex:1;min-width:0">
                  <strong class="mono pequeno">{{ item.aghu }}</strong>
                  <span class="pequeno"> {{ item.produto }}</span><br>
                  <span class="suave pequeno">
                    Lote {{ item.lote }} · val. {{ item.validade }}<template v-if="item.prontuario"> · prontuário {{ item.prontuario }}</template>
                    <template v-if="item.id_caixa"> · <strong>na caixa {{ item.id_caixa }}</strong></template>
                  </span>
                </span>
              </label>
            </div>
            <div class="campo" style="margin-top:.9rem">
              <label class="obrigatorio pequeno">O que houve com os itens marcados?</label>
              <input type="text" name="motivo" data-sem-foco="1" placeholder="Ex.: não chegou junto com a remessa">
            </div>
            <div class="campo">
              <label class="pequeno">Destino</label>
              <select name="destino" data-sem-foco="1">
                <option value="divergencia">Marcar como divergência</option>
                <option value="baixado">Baixar item (perda/avaria)</option>
              </select>
            </div>
            <button class="botao secundario" style="width:100%" data-sem-foco="1">Encerrar etapa tratando os marcados</button>
          </form>
          <p v-else class="vazio">Nada pendente nesta etapa.</p>
        </div>
      </aside>
    </div>

    <ConfirmacaoBip ref="conf" @fechou="aoFecharConfirmacao" />

    <AvisoValidade v-if="avisoValidade" :aviso="avisoValidade.dados" :enviando="enviandoCiencia"
                   @ciente="cienteValidade" @cancelar="cancelarValidade" />

    <!-- Escolha: o código bipado responde a mais de um item -->
    <div v-if="escolha" id="janela-escolha" class="confirmacao-bip escolha" role="alertdialog">
      <div class="confirmacao-bip-janela">
        <div class="confirmacao-bip-icone">?</div>
        <h2>{{ escolha.loteNaoEncontrado ? 'LOTE NÃO ENCONTRADO' : 'ATENÇÃO!' }}</h2>
        <p v-if="escolha.loteNaoEncontrado" class="escolha-explica" id="escolha-lote-nao-encontrado"
           style="color:var(--vermelho, #b3261e);font-weight:700">
          O lote da etiqueta (<span class="mono">{{ escolha.loteNaoEncontrado }}</span>) não está cadastrado.
          NADA foi registrado. Confira a embalagem: se o material for mesmo um destes lotes, clique nele.</p>
        <p v-else class="escolha-explica">O código <b class="mono">{{ escolha.codigo }}</b> corresponde a
          {{ escolha.opcoes.length }} itens diferentes. Verifique o lote e a validade na embalagem e clique no item certo.</p>
        <div class="escolha-lista">
          <button v-for="(o, i) in escolha.opcoes" :key="o.id_unidade" type="button" class="escolha-opcao" data-sem-foco="1" @click="escolher(o.id_unidade)">
            <span class="escolha-num">{{ i + 1 }}</span>
            <span class="escolha-texto">
              <span class="escolha-produto">AGHU <mark v-if="difere.aghu" class="escolha-difere"><b class="mono">{{ o.aghu }}</b></mark><b v-else class="mono">{{ o.aghu }}</b></span>
              <span class="escolha-dados" style="font-weight:600">
                <template v-if="o.descricao_aghu">{{ o.descricao_aghu }}</template>
                <span v-else class="suave">sem descrição do AGHU no catálogo — {{ o.produto_fornecedor || o.produto }}</span>
              </span>
              <span class="escolha-dados">
                lote <mark v-if="difere.lote" class="escolha-difere"><b class="mono">{{ o.lote }}</b></mark><b v-else class="mono">{{ o.lote }}</b> ·
                val. <mark v-if="difere.validade" class="escolha-difere">{{ o.validade }}</mark><template v-else>{{ o.validade }}</template> ·
                marca <mark v-if="difere.marca" class="escolha-difere">{{ o.marca }}</mark><template v-else>{{ o.marca }}</template>
              </span>
              <span v-if="difere.caixa || o.caixa" class="escolha-dados">
                <mark v-if="difere.caixa" class="escolha-difere"><template v-if="o.caixa">na caixa <b class="mono">{{ o.caixa }}</b></template><template v-else>fora de caixa (estoque solto)</template></mark>
                <template v-else><template v-if="o.caixa">na caixa <b class="mono">{{ o.caixa }}</b></template><template v-else>fora de caixa (estoque solto)</template></template>
              </span>
              <span class="escolha-forn">{{ o.fornecedor }}</span>
            </span>
          </button>
        </div>
        <button type="button" class="botao secundario" data-sem-foco="1" style="margin-top:.8rem" @click="cancelarEscolha">Nenhum destes — cancelar esta leitura</button>
      </div>
    </div>

    <!-- Entrega da caixa ao paciente: aviso vermelho com alarme, só fecha com a ciência -->
    <div v-if="alertaEntrega" id="alerta-entrega" class="alerta-entrega" role="alertdialog" aria-modal="true">
      <div class="alerta-entrega-janela">
        <div class="alerta-entrega-icone">!</div>
        <h2>RECOLHER A CAIXA E ENTREGAR AO PACIENTE</h2>
        <p class="alerta-entrega-produto">{{ alertaEntrega.produto }}</p>
        <p class="alerta-entrega-detalhe">AGHU {{ alertaEntrega.aghu }} · lote {{ alertaEntrega.lote }}</p>
        <p>Este material exige que a caixa/embalagem seja guardada e entregue ao paciente.</p>
        <button type="button" class="botao alerta-entrega-botao" id="alerta-entrega-ciente" ref="botaoCiente" data-sem-foco="1"
                :disabled="registrandoCiencia" @click="registrarCiencia">
          Estou ciente — vou entregar a caixa ao paciente
        </button>
      </div>
    </div>

    <!-- Devolução de caixa de consignado: quantidade digitada -->
    <div v-if="caixaQuantidade" id="quantidade-caixa" class="confirmacao-bip" role="dialog" aria-modal="true">
      <div class="confirmacao-bip-janela" style="border-color:var(--azul)">
        <h2 style="color:var(--azul)">Devolução da caixa <span class="mono">{{ caixaQuantidade.id_caixa }}</span></h2>
        <p class="confirmacao-bip-produto">{{ caixaQuantidade.nome }}<template v-if="caixaQuantidade.fornecedor"> · {{ caixaQuantidade.fornecedor }}</template></p>
        <div class="campo" style="max-width:260px;margin:0 auto">
          <label for="qc-quantidade" class="obrigatorio">Quantos itens estão voltando nesta caixa?</label>
          <input type="number" id="qc-quantidade" ref="campoQtdCaixa" v-model="qtdCaixa" min="0" step="1" inputmode="numeric" data-sem-foco="1"
                 style="font-size:1.6rem;text-align:center" @keydown.enter.prevent.stop="confirmarQuantidade">
        </div>
        <p class="suave pequeno">Conte os itens dentro da caixa. Se não bater com o sistema, a devolução
           não é registrada e a caixa fica bloqueada para conferência.</p>
        <div class="linha-botoes" style="justify-content:center">
          <button type="button" class="botao" data-sem-foco="1" @click="confirmarQuantidade">Registrar devolução da caixa</button>
          <button type="button" class="botao secundario" data-sem-foco="1" @click="fecharQuantidade">Cancelar</button>
        </div>
      </div>
    </div>

    <!-- Seleção manual pelo código AGHU (não deu para bipar) -->
    <div v-if="manual.aberta" id="selecao-manual" class="confirmacao-bip escolha" role="dialog" aria-modal="true">
      <div class="confirmacao-bip-janela" style="text-align:left;border-color:#d18f00;max-width:780px">
        <h2 style="color:#8a5a00;margin-top:0">Selecionar pelo código AGHU ou nome</h2>
        <p class="pequeno">Use <strong>só quando não for possível bipar</strong>. A escolha passa pelas mesmas
          conferências do bip e fica registrada com o motivo e o seu usuário.</p>
        <div class="grade grade-2">
          <div class="campo"><label class="obrigatorio" for="sm-motivo">Por que não foi possível bipar?</label>
            <select id="sm-motivo" ref="campoManualMotivo" v-model="manual.motivo" data-sem-foco="1">
              <option value="">— escolha —</option>
              <option v-for="m in d.motivos_selecao_manual" :key="m">{{ m }}</option>
            </select></div>
          <div class="campo"><label class="obrigatorio" for="sm-aghu">Código AGHU ou nome do material</label>
            <div style="display:flex;gap:.5rem">
              <input type="text" id="sm-aghu" ref="campoManualAghu" v-model="manual.aghu" data-sem-foco="1"
                     autocomplete="off" placeholder="ex.: 89846 ou parafuso cortical" @input="digitandoManual"
                     @keydown.enter.prevent="buscarManual">
              <button type="button" class="botao secundario" data-sem-foco="1" @click="buscarManual">Buscar</button>
            </div></div>
        </div>
        <div style="margin-top:.6rem;max-height:55vh;overflow:auto">
          <div v-if="manual.erro" class="aviso erro">{{ manual.erro }}</div>
          <p v-if="manual.buscando" class="suave pequeno">Buscando…</p>
          <p v-else-if="manual.grupos.length" class="suave pequeno" style="margin:.2rem 0 .4rem">{{ manual.grupos.length }} opção(ões){{ manual.grupos.length >= 40 ? ' — digite mais para refinar' : '' }}. Confira lote e validade na embalagem.</p>
          <div v-if="!manual.buscando && manual.buscou && !manual.grupos.length" class="aviso">Nada encontrado para “{{ manual.aghuBuscado }}” disponível para esta operação<template v-if="caixaAtiva"> na caixa {{ caixaAtiva.id_caixa }}</template>.</div>
          <button v-for="g in manual.grupos" :key="g.id_unidade" type="button" class="escolha-opcao" data-sem-foco="1" style="width:100%;text-align:left;margin-bottom:.4rem"
                  @click="escolherManual(g.id_unidade)">
            <span><strong class="mono">AGHU {{ g.aghu }}</strong> · {{ g.descricao }}<br>
              <span class="mono">lote <strong>{{ g.lote }}</strong> · val. <strong>{{ g.validade }}</strong></span>
              <span class="suave pequeno"> · {{ g.quantidade }} unidade(s)<template v-if="g.caixa"> · caixa {{ g.caixa }}</template><template v-if="g.dispensado"> · dispensado para este paciente</template></span></span>
          </button>
        </div>
        <button type="button" class="botao secundario" data-sem-foco="1" style="margin-top:.8rem" @click="fecharManual">Cancelar</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import AvisoValidade from '../../components/opme/AvisoValidade.vue';
import CancelarProcedimento from '../../components/opme/CancelarProcedimento.vue';
import ConfirmacaoBip from '../../components/opme/ConfirmacaoBip.vue';
import ResultadoLeitura from '../../components/opme/ResultadoLeitura.vue';
import SolicitacaoPainel from '../../components/opme/SolicitacaoPainel.vue';
import { useLeitor } from '../../composables/useLeitor';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const emit = defineEmits<{ (e: 'recarregar'): void }>();
const route = useRoute();
const { postJson, getJson, f } = useTela();

const op = computed(() => props.d.op);
const operacao = computed<string>(() => props.d.operacao);
const at = computed(() => props.d.atendimento);
const idAtendimento = computed(() => at.value?.id_atendimento || '');
const paciente = computed(() => at.value
  ? `Prontuário ${at.value.prontuario}${at.value.paciente ? ' · ' + at.value.paciente : ''}` : '');

// ----------------------------------------------------------- estado da tela
const campo = ref<HTMLInputElement | null>(null);
const resultado = ref<InstanceType<typeof ResultadoLeitura> | null>(null);
const conf = ref<InstanceType<typeof ConfirmacaoBip> | null>(null);
const campoMotivo = ref<HTMLInputElement | null>(null);
const codigo = ref('');
const som = ref(true);
const motivo = ref('');
const observacao = ref('');
// v18: devoluções ao fornecedor abertas de quem está bipando
const devAbertas = ref<any[]>([]);
async function carregarDevAbertas() {
  try {
    const r: any = await getJson('/almoxarifado/devolucoes-fornecedor/abertas');
    devAbertas.value = r.abertas || [];
  } catch { /* painel informativo */ }
}
// v18: problema do material (caiu no chão, veio danificado…)
const avariaProx = ref('');
const avariaDetalhe = ref('');
const sinalizando = ref('');
const sinalMotivo = ref('');
const sinalDetalhe = ref('');
async function enviarSinal(idUnidade: string) {
  if (!sinalMotivo.value) return;
  try {
    const r: any = await postJson('/api/avaria', {
      id_unidade: idUnidade, atendimento: idAtendimento.value, motivo: sinalMotivo.value, detalhe: sinalDetalhe.value,
    });
    resultado.value?.mostrar(!!r.ok, r.ok ? 'Problema registrado' : 'Não foi possível', r.mensagem);
    if (r.uso) uso.value = r.uso;
    if (r.ok) sinalizando.value = '';
  } catch {
    resultado.value?.mostrar(false, 'Falha de conexão', 'Tente de novo.');
  }
}
const extrasAbertos = ref(false);
const farmaciaDestino = ref(Object.keys(props.d.farmacias || {})[0] || '');
const resumo = ref<any>(props.d.resumo);
const uso = ref<any>(props.d.uso_registrado);
const ultimoUso = ref('');
const solicitacao = ref<any>(props.d.solicitacao);
const pendentes = ref<any[]>([...(props.d.pendentes || [])]);
const pendentesMarcados = ref<string[]>([]);
const contadorPendentes = ref<number>((props.d.pendentes || []).length);
const lidos = ref(0);
const listaLidos = ref<any[]>([]);
const naoRegistrado = ref('');
const mostrarProntoParaLer = ref(!['dispensar_sala', 'registrar_uso'].includes(props.d.operacao));
const travasDeTela = reactive({ falha: false, escolha: false, alerta: false, quantidade: false, manual: false, validade: false });
const { bip, vibrar, focar, bloquear } = useLeitor(campo, { somLigado: som });

// Lista "saiu da farmácia — aguardando a sala" (dispensação), redesenhada a cada leitura.
function linhaDispensacao(i: any) {
  return {
    tipo: 'item', aghu: i.codigo_aghu || '—', descricao: i.descritivo_hospital || i.xProd,
    lote: i.nLote || '—', validade: f.dataBr(i.dVal) || '—', id_caixa: i.id_caixa,
    quando: f.dataHoraBr(i.bipado_em), por: i.bipado_por, remover: `/dispensacoes/item/${i.id_item}/remover`,
  };
}
const pendenteLista = ref<any[]>((props.d.dispensacao_itens || []).map(linhaDispensacao));
const pendenteContagem = ref<{ itens: number; caixas: number } | null>(null);
// v18.11.8: a caixa aparece numa linha só ("Caixa CX-… — N item(ns)"), separada dos
// itens soltos — como na lista da sala.
const pendenteAgrupado = computed(() => {
  const caixas = new Map<string, any>();
  const soltos: any[] = [];
  for (const i of pendenteLista.value) {
    if (i.tipo === 'caixa') { caixas.set(i.id_caixa, { ...i }); continue; }
    if (!i.id_caixa) { soltos.push(i); continue; }
    const g = caixas.get(i.id_caixa);
    if (g) { g.quantidade = (g.quantidade || 0) + 1; g.novo = g.novo || i.novo; }
    else caixas.set(i.id_caixa, { ...i, tipo: 'caixa', quantidade: 1 });
  }
  return [...caixas.values(), ...soltos];
});
const contagemPendente = computed(() => {
  const soltos = pendenteAgrupado.value.filter((i: any) => i.tipo !== 'caixa').length;
  const nCx = pendenteAgrupado.value.length - soltos;
  if (nCx || !pendenteContagem.value) {
    const p: string[] = [];
    if (nCx) p.push(nCx === 1 ? '1 caixa' : `${nCx} caixas`);
    if (soltos) p.push(soltos === 1 ? '1 item' : `${soltos} itens`);
    return p.join(' e ') || 'nenhum item';
  }
  const p: string[] = [];
  const { itens, caixas } = pendenteContagem.value;
  if (itens) p.push(itens === 1 ? '1 item' : `${itens} itens`);
  if (caixas) p.push(caixas === 1 ? '1 caixa' : `${caixas} caixas`);
  return p.join(' e ') || 'nenhum item';
});

// v18.10: sala fechada trava o campo até "Abrir sala agora".
const salaFechada = ref(!!props.d.sala_fechada);
const abrindoSala = ref(false);
const erroAbrirSala = ref('');
async function abrirSalaAgora() {
  abrindoSala.value = true;
  erroAbrirSala.value = '';
  try {
    const r: any = await postJson('/api/abrir-sala', { atendimento: idAtendimento.value });
    if (r.ok) {
      salaFechada.value = false;
      resultado.value?.mostrar(true, 'Sala aberta', r.mensagem);
      nextTick(() => { sincronizarTrava(); campo.value?.focus(); });
    } else erroAbrirSala.value = r.mensagem;
  } catch {
    erroAbrirSala.value = 'Falha de conexão. Tente de novo.';
  } finally {
    abrindoSala.value = false;
  }
}

const campoTravado = computed(() =>
  salaFechada.value || travasDeTela.falha || travasDeTela.escolha || travasDeTela.alerta || travasDeTela.quantidade || travasDeTela.manual
  || travasDeTela.validade
  || (!!op.value.confirmacao_papel && !entrega.value));

function sincronizarTrava() {
  bloquear(campoTravado.value);
}
if (salaFechada.value) bloquear(true);

// ----------------------------------------------------------- entrega conferida na hora
// A senha de quem recebe é digitada UMA vez e vale para os materiais desta entrega.
// Enquanto está aberta, o nome de quem confirmou fica na tela com a contagem, e ela
// se fecha sozinha por inatividade. O servidor confere a senha em CADA leitura.
const ENTREGA_INATIVIDADE = 5 * 60 * 1000;
const usuarioResponsavel = ref('');
const senhaResponsavel = ref('');
const abrindoEntrega = ref(false);
const entrega = ref<{ username: string; senha: string; nome: string; itens: number } | null>(null);
let relogioEntrega: ReturnType<typeof setTimeout> | null = null;
const textoContagemEntrega = computed(() => {
  const n = entrega.value?.itens || 0;
  if (!n) return 'nenhum material bipado ainda';
  return n === 1 ? '1 material bipado' : `${n} materiais bipados`;
});

function marcarAtividadeDaEntrega() {
  if (!entrega.value) return;
  if (relogioEntrega) clearTimeout(relogioEntrega);
  relogioEntrega = setTimeout(() => encerrarEntrega(
    'A entrega foi encerrada sozinha depois de alguns minutos parada. Para continuar, peça a senha de novo a quem recebe.'),
    ENTREGA_INATIVIDADE);
}

async function abrirEntrega() {
  if (!usuarioResponsavel.value) {
    resultado.value?.mostrar(false, 'Falta escolher quem recebe', 'Selecione a pessoa que está recebendo o material.');
    return;
  }
  if (!senhaResponsavel.value) {
    resultado.value?.mostrar(false, 'Falta a senha', 'A senha precisa ser digitada por quem está recebendo o material.');
    return;
  }
  abrindoEntrega.value = true;
  try {
    const r: any = await postJson('/api/abrir-entrega', {
      operacao: operacao.value, usuario_responsavel: usuarioResponsavel.value, senha_responsavel: senhaResponsavel.value,
    });
    if (r.ok) {
      entrega.value = { username: r.username, senha: senhaResponsavel.value, nome: r.nome, itens: 0 };
      senhaResponsavel.value = '';
      sincronizarTrava();
      marcarAtividadeDaEntrega();
      resultado.value?.mostrar(true, `Entrega aberta por ${r.nome}`, 'Pode bipar os materiais desta entrega.');
      bip(880, 0.12);
      await nextTick();
      focar();
    } else {
      senhaResponsavel.value = '';
      resultado.value?.mostrar(false, 'Não foi possível abrir a entrega', r.mensagem);
      bip(200, 0.3);
    }
  } catch {
    resultado.value?.mostrar(false, 'Falha de conexão', 'Verifique a rede e tente de novo.');
    bip(200, 0.3);
  } finally {
    abrindoEntrega.value = false;
  }
}

function encerrarEntrega(aviso?: string) {
  if (relogioEntrega) clearTimeout(relogioEntrega);
  const encerrada = entrega.value;
  entrega.value = null;
  usuarioResponsavel.value = '';
  senhaResponsavel.value = '';
  sincronizarTrava();
  if (encerrada) {
    const quantos = encerrada.itens === 1 ? '1 material' : `${encerrada.itens} materiais`;
    resultado.value?.mostrar(true, 'Entrega encerrada', aviso || `${quantos} conferidos por ${encerrada.nome}.`);
  }
}

// ----------------------------------------------------------- caixa ativa (registro de uso)
// Para registrar o uso de um item de caixa, a sala bipa primeiro a CAIXA (ela fica
// "ativa") e depois o item; o servidor só aceita o item se ele estiver nela.
const chaveCaixa = `traceopme-caixa-ativa-${idAtendimento.value}`;
const caixaAtiva = ref<any>(null);
if (operacao.value === 'registrar_uso') {
  try {
    const salva = sessionStorage.getItem(chaveCaixa);
    if (salva) caixaAtiva.value = JSON.parse(salva);
  } catch { /* ignora */ }
}
function definirCaixaAtiva(caixa: any) {
  caixaAtiva.value = caixa || null;
  try {
    if (caixa) sessionStorage.setItem(chaveCaixa, JSON.stringify(caixa));
    else sessionStorage.removeItem(chaveCaixa);
  } catch { /* sem armazenamento */ }
}
function sairDaCaixa() {
  definirCaixaAtiva(null);
  resultado.value?.mostrar(true, 'Fora de caixa', 'Os próximos itens são do estoque solto.');
  focar();
}

// ----------------------------------------------------------- confirmação grande
async function aoFecharConfirmacao(falha: boolean) {
  if (falha) {
    travasDeTela.falha = false;
    sincronizarTrava();
    await nextTick();
    if (naoRegistrado.value && !codigo.value) {
      codigo.value = naoRegistrado.value;
      await nextTick();
      focar();
      campo.value?.select();
      return;
    }
  }
  focar();
}
function confirmar(ok: boolean, titulo: string, produto = '', detalhe = '', alertas: string[] = []) {
  if (!ok) { travasDeTela.falha = true; sincronizarTrava(); }
  conf.value?.mostrar(ok, titulo, produto, detalhe, alertas);
}

// ----------------------------------------------------------- escolha entre itens
const escolha = ref<{ codigo: string; opcoes: any[]; loteNaoEncontrado?: string } | null>(null);
const difere = computed(() => {
  const ops = escolha.value?.opcoes || [];
  const dif = (campoOp: string) => new Set(ops.map((o: any) => String(o[campoOp] || ''))).size > 1;
  return { aghu: dif('aghu'), lote: dif('lote'), validade: dif('validade'), marca: dif('marca'), caixa: dif('caixa') };
});
function mostrarEscolha(opcoes: any[], codigoOriginal: string, loteNaoEncontrado = '') {
  escolha.value = { codigo: codigoOriginal, opcoes: opcoes || [], loteNaoEncontrado };
  travasDeTela.escolha = true;
  sincronizarTrava();
  campo.value?.blur();
  bip(660, 0.15); setTimeout(() => bip(660, 0.15), 220);
  vibrar([80, 60, 80]);
  resultado.value?.personalizado({ classe: '', estilo: 'background:var(--amarelo-claro)', icone: '?',
    titulo: 'Aguardando a escolha do item', detalhe: `O código ${codigoOriginal} responde a mais de um item.` });
}
function fecharEscolha() {
  escolha.value = null;
  travasDeTela.escolha = false;
  sincronizarTrava();
}
async function escolher(idUnidade: string) {
  const original = escolha.value?.codigo || '';
  fecharEscolha();
  await nextTick();
  enviar(original, idUnidade);
}
async function cancelarEscolha() {
  const original = escolha.value?.codigo || '';
  fecharEscolha();
  naoRegistrado.value = original;
  await nextTick();
  if (!codigo.value) { codigo.value = original; await nextTick(); campo.value?.select(); }
  focar();
  resultado.value?.mostrar(false, 'Leitura cancelada', 'Nada foi registrado. Bipe de novo quando quiser.');
}

// ----------------------------------------------------------- aviso de validade (nov/2026)
// Há, no mesmo estoque, lote do mesmo material que vence antes. Não trava: a
// pessoa troca de lote ou dá ciência — e só então a leitura é registrada.
const avisoValidade = ref<{ dados: any; codigo: string; selecaoManual: string } | null>(null);
const enviandoCiencia = ref(false);
function mostrarAvisoValidade(dados: any, cod: string, selecaoManual: string) {
  avisoValidade.value = { dados, codigo: cod, selecaoManual };
  travasDeTela.validade = true;
  sincronizarTrava();
  campo.value?.blur();
  bip(660, 0.15); setTimeout(() => bip(660, 0.15), 220);
  vibrar([80, 60, 80]);
  resultado.value?.personalizado({ classe: '', estilo: 'background:var(--amarelo-claro)', icone: '!',
    titulo: 'Aguardando a ciência', detalhe: 'Há lote do mesmo material que vence antes.' });
}
function fecharAvisoValidade() {
  avisoValidade.value = null;
  travasDeTela.validade = false;
  sincronizarTrava();
}
async function cienteValidade() {
  const a = avisoValidade.value;
  if (!a) return;
  fecharAvisoValidade();
  enviandoCiencia.value = true;
  await nextTick();
  try {
    await enviar(a.codigo, a.dados.escolhido?.id_unidade || '', null, '', a.selecaoManual, true);
  } finally {
    enviandoCiencia.value = false;
  }
}
async function cancelarValidade() {
  const a = avisoValidade.value;
  fecharAvisoValidade();
  if (a) naoRegistrado.value = a.codigo;
  await nextTick();
  focar();
  resultado.value?.mostrar(false, 'Leitura cancelada', 'Nada foi registrado. Bipe o lote que vence antes.');
}

// ----------------------------------------------------------- revisão de caixa
const revisao = ref<{ rev: any; codigo: string; fora: number[]; avisar: boolean } | null>(null);
const revisaoForaIds = computed(() => {
  if (!revisao.value) return [] as string[];
  const ids: string[] = [];
  revisao.value.rev.grupos.forEach((g: any, n: number) => {
    let q = Number(revisao.value!.fora[n]);
    if (Number.isNaN(q) || q < 0) q = 0;
    if (q > g.quantidade) q = g.quantidade;
    // Das unidades de um grupo (mesmo produto, lote e série), quais ficam de fora
    // não muda nada para a rastreabilidade: são idênticas.
    ids.push(...g.ids.slice(g.ids.length - q));
  });
  return ids;
});
const revisaoVai = computed(() => (revisao.value ? revisao.value.rev.total - revisaoForaIds.value.length : 0));
const textoConfirmarRevisao = computed(() => {
  if (!revisao.value) return '';
  const fora = revisaoForaIds.value.length;
  return fora
    ? `Confirmar ${revisaoVai.value} item(ns) · ${fora} ${revisao.value.rev.devolucao ? 'não está(ão)' : 'fica(m)'}`
    : `Confirmar ${revisao.value.rev.total} item(ns)`;
});
function limitarFora(n: number) {
  if (!revisao.value) return;
  const g = revisao.value.rev.grupos[n];
  if (revisao.value.fora[n] > g.quantidade) revisao.value.fora[n] = g.quantidade;
}
function confirmarRevisao() {
  if (!revisao.value) return;
  const excluir = [...revisaoForaIds.value];
  const cod = revisao.value.codigo;
  revisao.value = null;
  nextTick(() => enviar(cod, '', { excluir }));
}
function cancelarRevisao() {
  revisao.value = null;
  nextTick(() => {
    resultado.value?.mostrar(false, 'Conferência cancelada', 'Nada foi movido. Bipe a caixa de novo quando quiser.');
    focar();
  });
}

// ----------------------------------------------------------- entrega ao paciente (alarme)
const alertaEntrega = ref<any>(null);
const botaoCiente = ref<HTMLButtonElement | null>(null);
const registrandoCiencia = ref(false);
let alarme: ReturnType<typeof setInterval> | null = null;
async function mostrarAlertaEntrega(info: any) {
  alertaEntrega.value = info;
  travasDeTela.alerta = true;
  sincronizarTrava();
  let toques = 0;
  alarme = setInterval(() => {
    bip(toques % 2 ? 520 : 960, 0.22);
    toques += 1;
    if (toques >= 8 && alarme) { clearInterval(alarme); alarme = null; }
  }, 300);
  vibrar([200, 100, 200, 100, 200]);
  await nextTick();
  botaoCiente.value?.focus();
}
async function registrarCiencia() {
  if (!alertaEntrega.value) return;
  registrandoCiencia.value = true;
  try {
    const r: any = await postJson('/api/ciencia-entrega', { id_unidade: alertaEntrega.value.id_unidade });
    if (!r.ok) { alert(r.mensagem); return; }
    if (alarme) { clearInterval(alarme); alarme = null; }
    alertaEntrega.value = null;
    travasDeTela.alerta = false;
    sincronizarTrava();
    resultado.value?.mostrar(true, 'Ciência registrada', r.mensagem);
    await nextTick();
    focar();
  } catch {
    alert('Falha de conexão ao registrar a ciência. Tente de novo.');
  } finally {
    registrandoCiencia.value = false;
  }
}

// ----------------------------------------------------------- quantidade da caixa (devolução)
const caixaQuantidade = ref<any>(null);
const qtdCaixa = ref('');
const campoQtdCaixa = ref<HTMLInputElement | null>(null);
async function pedirQuantidade(caixa: any) {
  caixaQuantidade.value = caixa;
  qtdCaixa.value = '';
  travasDeTela.quantidade = true;
  sincronizarTrava();
  await nextTick();
  setTimeout(() => campoQtdCaixa.value?.focus(), 50);
}
function fecharQuantidade() {
  caixaQuantidade.value = null;
  travasDeTela.quantidade = false;
  sincronizarTrava();
  focar();
}
function confirmarQuantidade() {
  const v = String(qtdCaixa.value ?? '').trim();
  if (!/^\d+$/.test(v)) { campoQtdCaixa.value?.focus(); return; }
  const cod = caixaQuantidade.value.id_caixa;
  caixaQuantidade.value = null;
  travasDeTela.quantidade = false;
  sincronizarTrava();
  enviar(cod, '', null, v);
}

// ----------------------------------------------------------- seleção manual pelo AGHU
const manual = reactive({ aberta: false, motivo: '', aghu: '', aghuBuscado: '', grupos: [] as any[], buscando: false, buscou: false, erro: '' });
const campoManualMotivo = ref<HTMLSelectElement | null>(null);
const campoManualAghu = ref<HTMLInputElement | null>(null);
async function abrirManual() {
  Object.assign(manual, { aberta: true, aghu: '', grupos: [], buscou: false, erro: '' });
  travasDeTela.manual = true;
  sincronizarTrava();
  await nextTick();
  campoManualMotivo.value?.focus();
}
function fecharManual() {
  manual.aberta = false;
  manual.grupos = [];
  travasDeTela.manual = false;
  sincronizarTrava();
  focar();
}
// nov/2026: busca enquanto digita (código AGHU ou nome, a partir de 3 letras)
let esperaManual: ReturnType<typeof setTimeout> | undefined;
let buscaManualSeq = 0;
function digitandoManual() {
  clearTimeout(esperaManual);
  const t = manual.aghu.trim();
  if (!t || (t.length < 3 && !/^\d+$/.test(t))) { manual.grupos = []; manual.buscou = false; return; }
  esperaManual = setTimeout(buscarManual, 300);
}
async function buscarManual() {
  clearTimeout(esperaManual);
  const aghu = manual.aghu.trim();
  if (!aghu) { campoManualAghu.value?.focus(); return; }
  const seq = ++buscaManualSeq;
  manual.buscando = true;
  manual.erro = '';
  try {
    const r: any = await getJson('/api/selecao-manual', {
      operacao: operacao.value, aghu, atendimento: idAtendimento.value, caixa: caixaAtiva.value ? caixaAtiva.value.id_caixa : '',
    });
    if (seq !== buscaManualSeq) return; // chegou uma busca mais nova
    manual.grupos = r.grupos || [];
    manual.aghuBuscado = aghu;
    manual.buscou = true;
  } catch {
    if (seq === buscaManualSeq) manual.erro = 'Falha de conexão. Tente de novo.';
  } finally {
    if (seq === buscaManualSeq) manual.buscando = false;
  }
}
function escolherManual(id: string) {
  if (!manual.motivo) {
    manual.erro = 'Escolha primeiro o motivo.';
    campoManualMotivo.value?.focus();
    return;
  }
  const motivoManual = manual.motivo;
  fecharManual();
  enviar(id, id, null, '', motivoManual);
}

// ----------------------------------------------------------- envio da leitura
let ocupado = false;
let ultimoCodigo = '';
let ultimoInstante = 0;

function lerCampo() {
  const c = codigo.value.trim();
  if (c) enviar(c);
}

function atualizarDevolucao(dados: any) {
  if (!dados.devolucao) return;
  const dv = dados.devolucao;
  pendenteContagem.value = { itens: dv.itens || 0, caixas: dv.caixas || 0 };
  if (Array.isArray(dv.lista)) {
    pendenteLista.value = dv.lista.map((i: any) => ({ ...i, novo: true }));
  }
}

async function atualizarSolicitacao() {
  if (operacao.value !== 'dispensar_sala' || !idAtendimento.value) return;
  try {
    const env: any = await getJson(`/farmacia/atendimento/${idAtendimento.value}/solicitacao/painel`);
    if (env?.dados?.sol) solicitacao.value = env.dados.sol;
  } catch { /* sem rede: fica o que estava; o próximo bip atualiza */ }
}

function atualizarContadores(dados: any) {
  if (typeof dados.pendentes === 'number') contadorPendentes.value = dados.pendentes;
  if (dados.resumo) resumo.value = dados.resumo;
}

function atualizarUso(dados: any) {
  if (!dados || !dados.uso || !Array.isArray(dados.uso.lista)) return;
  uso.value = dados.uso;
  ultimoUso.value = dados.item?.id_unidade || '';
}

function removerDosPendentes(id: string) {
  pendentes.value = pendentes.value.filter((p) => p.id_unidade !== id);
}

async function enviar(cod: string, idUnidadeEscolhida = '', conferencia: { excluir: string[] } | null = null,
                      quantidadeCaixa = '', selecaoManual = '', cienciaValidade = false) {
  if (ocupado || alertaEntrega.value || caixaQuantidade.value || escolha.value || manual.aberta || avisoValidade.value) return;
  if (revisao.value && !conferencia) {
    revisao.value.avisar = true;
    bip(200, 0.3);
    return;
  }
  if (op.value.confirmacao_papel && !entrega.value) {
    resultado.value?.mostrar(false, 'Entrega não está aberta', 'Quem recebe o material precisa confirmar com a senha antes da primeira leitura.');
    bip(200, 0.3);
    return;
  }
  const agora = Date.now();
  // A checagem de leitura repetida não vale quando é a resposta a uma escolha.
  if (!idUnidadeEscolhida && !conferencia && !quantidadeCaixa && !cienciaValidade && cod === ultimoCodigo && agora - ultimoInstante < 1200) {
    resultado.value?.mostrar(false, 'Leitura repetida', 'O mesmo código foi lido duas vezes seguidas. Aguarde um instante.');
    bip(220, 0.18);
    return;
  }
  ultimoCodigo = cod;
  ultimoInstante = agora;
  ocupado = true;
  codigo.value = '';
  mostrarProntoParaLer.value = false;

  try {
    const dados: any = await postJson('/api/bipar', {
      operacao: operacao.value,
      codigo: cod,
      atendimento: idAtendimento.value,
      motivo: motivo.value,
      observacao: observacao.value,
      farmacia: op.value.define_farmacia ? farmaciaDestino.value : (props.d.farmacia || ''),
      id_unidade: idUnidadeEscolhida || '',
      selecao_manual: selecaoManual || '',
      revisado: !!conferencia,
      excluir: conferencia ? conferencia.excluir : [],
      quantidade: quantidadeCaixa || '',
      caixa: caixaAtiva.value ? caixaAtiva.value.id_caixa : '',
      devolvido_por: '',
      usuario_responsavel: entrega.value ? entrega.value.username : '',
      senha_responsavel: entrega.value ? entrega.value.senha : '',
      ciencia_validade: cienciaValidade,
      // v18: problema do material marcado antes do bip (caiu, danificado…)
      avaria: operacao.value === 'registrar_uso' ? avariaProx.value : '',
      avaria_detalhe: operacao.value === 'registrar_uso' ? avariaDetalhe.value : '',
    });
    if (dados.ok && dados.item && operacao.value === 'registrar_uso') { avariaProx.value = ''; avariaDetalhe.value = ''; }
    if (Array.isArray(dados.devolucoes_abertas)) devAbertas.value = dados.devolucoes_abertas;

    if (dados.ok && dados.caixa_ativa) {
      definirCaixaAtiva(dados.caixa_ativa);
      resultado.value?.mostrar(true, `Caixa ${dados.caixa_ativa.id_caixa} selecionada`, dados.mensagem);
      confirmar(true, 'CAIXA SELECIONADA', `${dados.caixa_ativa.id_caixa} — ${dados.caixa_ativa.nome}`,
        'Agora bipe o item que saiu desta caixa.');
      bip(660, 0.1);
    } else if (dados.pede_quantidade && dados.caixa) {
      pedirQuantidade(dados.caixa);
      bip(440, 0.15);
    } else if (dados.revisao_caixa) {
      revisao.value = { rev: dados.revisao_caixa, codigo: cod, fora: dados.revisao_caixa.grupos.map(() => 0), avisar: false };
      bip(440, 0.15);
    } else if (dados.aviso_validade) {
      mostrarAvisoValidade(dados, cod, selecaoManual);
    } else if (dados.escolha) {
      mostrarEscolha(dados.opcoes, cod, dados.lote_nao_encontrado || '');
      bip(dados.lote_nao_encontrado ? 200 : 440, dados.lote_nao_encontrado ? 0.3 : 0.15);
    } else if (dados.ok && dados.caixa) {
      // Uma leitura moveu a caixa inteira: a lista mostra uma linha só.
      lidos.value += 1;
      if (entrega.value) entrega.value.itens += dados.caixa.total || 0;
      listaLidos.value.unshift({ chave: `cx-${dados.caixa.id_caixa}-${Date.now()}`, n: lidos.value, caixa: dados.caixa });
      (dados.itens || []).forEach((i: any) => removerDosPendentes(i.id_unidade));
      const detalheCaixa = (dados.excluidos && dados.excluidos.length) ? dados.mensagem : `${dados.caixa.total} item(ns) movidos de uma vez`;
      resultado.value?.mostrar(true, `${dados.caixa.id_caixa} — ${dados.caixa.nome}`, detalheCaixa, dados.alertas);
      atualizarDevolucao(dados);
      confirmar(true,
        operacao.value === 'dispensar_sala' ? 'CAIXA DISPENSADA PARA A SALA'
          : (dados.pendente ? 'CAIXA BIPADA NA DEVOLUÇÃO' : 'DEVOLUÇÃO DA CAIXA REGISTRADA'),
        `${dados.caixa.id_caixa} — ${dados.caixa.nome}`,
        `${dados.caixa.total} item(ns) — contagem confere` + (paciente.value ? `\n${paciente.value}` : '')
          + (dados.pendente ? (operacao.value === 'dispensar_sala' ? '\nAguardando a ciência da sala' : '\nAguardando a confirmação da farmácia') : '')
          + (dados.devolvido_por ? `\nDevolvido por ${dados.devolvido_por}` : '')
          + (dados.recebido_por ? `\nRecebido por ${dados.recebido_por}` : ''),
        dados.alertas);
      bip((dados.alertas && dados.alertas.length) ? 660 : 880, 0.18);
      vibrar([40, 40, 40]);
    } else if (dados.ok) {
      lidos.value += 1;
      if (entrega.value) entrega.value.itens += 1;
      listaLidos.value.unshift({ chave: `u-${dados.item.id_unidade}-${Date.now()}`, n: lidos.value, item: dados.item });
      if (dados.entrega_paciente) {
        mostrarAlertaEntrega(dados.entrega_paciente);
      } else {
        const op = operacao.value;
        confirmar(true,
          op === 'registrar_uso' ? 'USO REGISTRADO'
            : (op === 'devolver_nao_utilizado' ? 'BIPADO NA DEVOLUÇÃO'
              : (op === 'dispensar_sala'
                ? (dados.nao_solicitado ? 'DISPENSADO — NÃO ESTAVA NA SOLICITAÇÃO' : 'DISPENSADO PARA A SALA')
                : 'LEITURA REGISTRADA')),
          dados.item.produto,
          `AGHU ${dados.item.aghu} · lote ${dados.item.lote} · validade ${dados.item.validade}`
            + (paciente.value && ['registrar_uso', 'devolver_nao_utilizado', 'dispensar_sala'].includes(op) ? `\n${paciente.value}` : '')
            + (dados.empenho && !(dados.alertas || []).includes(dados.empenho) ? `\n${dados.empenho}` : '')
            + (op === 'registrar_uso' && caixaAtiva.value ? `\nDa caixa ${caixaAtiva.value.id_caixa}` : '')
            + (dados.devolvido_por ? `\nDevolvido por ${dados.devolvido_por}` : '')
            + (dados.pendente ? (op === 'dispensar_sala' ? '\nAguardando a ciência da sala' : '\nAguardando a confirmação da farmácia') : '')
            + (dados.recebido_por ? `\nRecebido por ${dados.recebido_por}` : '')
            + (dados.selecao_manual ? `\nSelecionado pelo AGHU (sem bipar) — ${dados.selecao_manual}` : ''),
          dados.alertas);
        atualizarDevolucao(dados);
      }
      removerDosPendentes(dados.item.id_unidade);
      resultado.value?.mostrar(true, dados.item.produto,
        `AGHU ${dados.item.aghu} · lote ${dados.item.lote} · validade ${dados.item.validade}`, dados.alertas);
      bip((dados.alertas && dados.alertas.length) ? 660 : 880, 0.12);
      vibrar(40);
    } else if (dados.sala_fechada) {
      salaFechada.value = true;
      nextTick(sincronizarTrava);
      bip(200, 0.3);
    } else {
      naoRegistrado.value = cod;
      resultado.value?.mostrar(false, 'Não foi possível registrar', dados.mensagem);
      if (/justificativa|motivo no campo/i.test(dados.mensagem || '')) {
        extrasAbertos.value = true;
        setTimeout(() => campoMotivo.value?.focus(), 50);
      }
      confirmar(false, 'NÃO REGISTRADO', `Código lido: ${cod}`, dados.mensagem);
      bip(200, 0.3);
      vibrar([60, 50, 60]);
    }
    if (dados.ok) naoRegistrado.value = '';
    atualizarUso(dados);
    if (dados.ok) atualizarSolicitacao();
    atualizarContadores(dados);
  } catch (e: any) {
    naoRegistrado.value = cod;
    const detalhe = e?.response?.data?.mensagem || e?.response?.data?.detail || 'Verifique a rede e leia o código novamente.';
    resultado.value?.mostrar(false, 'Falha de conexão', detalhe);
    confirmar(false, 'NÃO REGISTRADO', `Código lido: ${cod}`, detalhe);
    bip(200, 0.3);
  } finally {
    ocupado = false;
    // Bipar é atividade: a entrega só expira quando a leitura realmente para.
    marcarAtividadeDaEntrega();
    focar();
  }
}

// ----------------------------------------------------------- excluir bip (registro de uso)
const excluindo = ref('');
const motivoExclusao = ref('');
const enviandoExclusao = ref(false);
const campoMotivoExclusao = ref<HTMLInputElement[] | HTMLInputElement | null>(null);
async function iniciarExclusao(id: string) {
  excluindo.value = id;
  motivoExclusao.value = '';
  await nextTick();
  const el = Array.isArray(campoMotivoExclusao.value) ? campoMotivoExclusao.value[0] : campoMotivoExclusao.value;
  el?.focus();
}
function cancelarExclusao() {
  excluindo.value = '';
  focar();
}
async function confirmarExclusao(id: string) {
  if (!motivoExclusao.value.trim()) {
    resultado.value?.mostrar(false, 'Informe o motivo', 'Escolha ou escreva por que o bip está sendo excluído.');
    return;
  }
  enviandoExclusao.value = true;
  try {
    const r: any = await postJson('/api/excluir-uso', { atendimento: idAtendimento.value, id_unidade: id, motivo: motivoExclusao.value.trim() });
    resultado.value?.mostrar(r.ok, r.ok ? 'Bip excluído' : 'Não foi possível excluir', r.mensagem);
    if (r.ok) bip(520, 0.12); else bip(200, 0.3);
    if (r.uso) { uso.value = r.uso; ultimoUso.value = ''; }
    atualizarContadores(r);
    excluindo.value = '';
  } catch {
    resultado.value?.mostrar(false, 'Falha de conexão', 'Verifique a rede e tente de novo.');
  } finally {
    enviandoExclusao.value = false;
    focar();
  }
}

// ----------------------------------------------------------- desfazer
async function desfazer(id: string) {
  if (!confirm('Desfazer o último movimento deste item?')) { focar(); return; }
  const r: any = await postJson('/api/desfazer', { id_unidade: id, motivo: 'Correção na tela de bipagem' });
  resultado.value?.mostrar(r.ok, r.ok ? 'Movimento desfeito' : 'Não foi possível desfazer', r.mensagem);
  if (r.ok) {
    listaLidos.value = listaLidos.value.filter((l) => l.item?.id_unidade !== id);
    lidos.value = Math.max(0, lidos.value - 1);
    if (operacao.value === 'devolver_fornecedor') carregarDevAbertas();
    setTimeout(() => emit('recarregar'), 900);
  }
  focar();
}

function marcarTodosPendentes(e: Event) {
  pendentesMarcados.value = (e.target as HTMLInputElement).checked ? pendentes.value.map((p) => p.id_unidade) : [];
}

if (operacao.value === 'devolver_fornecedor') carregarDevAbertas();

onBeforeUnmount(() => {
  if (alarme) clearInterval(alarme);
  if (relogioEntrega) clearTimeout(relogioEntrega);
});
</script>
