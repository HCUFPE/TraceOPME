/**
 * Registro das telas do TraceOPME.
 *
 * O backend devolve, para cada endereço, o nome da "tela" (o mesmo nome do
 * template da v17, ex.: "almoxarifado/nf_detalhe.html") e os dados. Aqui cada
 * nome aponta para a view Vue que desenha aquela tela. As views são carregadas
 * sob demanda (code splitting do Vite).
 */
export interface DefinicaoTela {
  titulo: string | ((d: any) => string);
  componente: () => Promise<any>;
  /** A própria view mostra `d.erro` (sem a faixa genérica do topo). */
  erroNaTela?: boolean;
}

/** v18.10: telas de acompanhamento que se atualizam sozinhas (sem perder o que está sendo digitado). */
export const TELAS_AUTO = new Set([
  'painel.html', 'almoxarifado/hub.html', 'almoxarifado/envios.html', 'almoxarifado/devolucoes_farmacia.html',
  'farmacia/hub.html', 'farmacia/recebimentos.html', 'farmacia/solicitacoes.html', 'farmacia/dispensacoes.html',
  'farmacia/devolucoes.html', 'farmacia/a_concluir.html', 'farmacia/usos_sem_dispensacao.html', 'farmacia/nao_recebidos.html',
  'farmacia/nota_consumo.html', 'farmacia/atendimentos.html', 'farmacia/devolucoes_almox.html', 'farmacia/transferencias.html',
  'farmacia/caixas_sala.html', 'sala_procedimento/hub.html', 'sala_procedimento/salas.html',
  'sala_procedimento/atendimentos.html', 'procedimentos/lista.html', 'qg/painel.html',
]);
export const SEGUNDOS_AUTO = 45;

export const TELAS: Record<string, DefinicaoTela> = {
  // Painel e perfil
  'painel.html': { titulo: 'Painel', componente: () => import('./Painel.vue') },
  'perfil.html': { titulo: 'Meu perfil', componente: () => import('./Perfil.vue') },

  // Bipagem (todas as operações de leitura contínua)
  'bipagem.html': { titulo: (d) => d?.op?.titulo || 'Bipagem', componente: () => import('./Bipagem.vue') },

  // Almoxarifado
  'almoxarifado/hub.html': { titulo: 'Almoxarifado', componente: () => import('./AlmoxarifadoHub.vue') },
  'almoxarifado/manual.html': { titulo: 'Cadastro manual', componente: () => import('./AlmoxarifadoManual.vue') },
  'almoxarifado/etiquetas.html': { titulo: 'Etiquetas QR', componente: () => import('./AlmoxarifadoEtiquetas.vue') },
  'almoxarifado/nf_lista.html': { titulo: 'Entrada por NF', componente: () => import('./AlmoxarifadoNfLista.vue') },
  'almoxarifado/aghu_web.html': { titulo: (d) => d?.robo?.titulo ?? 'Lançar no AGHU', componente: () => import('./AlmoxarifadoAghuWeb.vue') },
  'almoxarifado/nf_detalhe.html': { titulo: (d) => `NF ${d?.nota?.numero_nf ?? ''}`, componente: () => import('./AlmoxarifadoNfDetalhe.vue') },
  'almoxarifado/envios.html': { titulo: 'Enviar para a farmácia', componente: () => import('./AlmoxarifadoEnvios.vue') },
  'almoxarifado/devolucoes_farmacia.html': { titulo: 'Devoluções das farmácias', componente: () => import('./AlmoxarifadoDevolucoesFarmacia.vue') },
  'almoxarifado/devolucao_farmacia.html': { titulo: (d) => `Devolução ${d?.rem?.id_remessa ?? ''}`, componente: () => import('./FarmaciaRecebimento.vue') },
  'farmacia/devolucoes_almox.html': { titulo: 'Devolver ao almoxarifado', componente: () => import('./FarmaciaDevolucoesAlmox.vue') },
  'farmacia/nota_consumo.html': { titulo: 'Nota de consumo e RM (AGHU)', componente: () => import('./FarmaciaNotaConsumo.vue') },
  'farmacia/nao_recebidos.html': { titulo: 'Não recebidos pela sala', componente: () => import('./FarmaciaNaoRecebidos.vue') },
  'farmacia/transferencias.html': { titulo: 'Transferir para outra farmácia', componente: () => import('./FarmaciaTransferencias.vue') },
  'farmacia/transferencia.html': { titulo: (d) => `Transferência ${d?.rem?.id_remessa ?? ''}`, componente: () => import('./AlmoxarifadoEnvio.vue') },
  'farmacia/devolucao_almox.html': { titulo: (d) => `Devolução ${d?.rem?.id_remessa ?? ''}`, componente: () => import('./AlmoxarifadoEnvio.vue') },
  'almoxarifado/devolucao_fornecedor.html': { titulo: 'Devolução ao fornecedor', componente: () => import('./AlmoxarifadoDevolucaoFornecedor.vue') },
  'almoxarifado/romaneios_fornecedor.html': { titulo: 'Devoluções ao fornecedor', componente: () => import('./AlmoxarifadoRomaneiosFornecedor.vue') },
  'almoxarifado/envio.html': { titulo: (d) => `Envio ${d?.rem?.id_remessa ?? ''}`, componente: () => import('./AlmoxarifadoEnvio.vue') },
  'almoxarifado/planilha.html': { titulo: 'Planilha de lotes do AGHU', componente: () => import('./AlmoxarifadoPlanilha.vue') },
  'almoxarifado/correcoes.html': { titulo: 'Correções', componente: () => import('./AlmoxarifadoCorrecoes.vue') },
  'almoxarifado/nao_cadastrados.html': { titulo: 'Material não cadastrado', componente: () => import('./AlmoxarifadoNaoCadastrados.vue') },

  // Farmácia
  'farmacia/hub.html': { titulo: 'Farmácia', componente: () => import('./FarmaciaHub.vue') },
  'farmacia/caixas_consignado.html': { titulo: 'Caixas de consignado', componente: () => import('./FarmaciaCaixasConsignado.vue') },
  'farmacia/caixa_consignado.html': { titulo: (d) => `Caixa ${d?.caixa?.id_caixa ?? ''}`, componente: () => import('./FarmaciaCaixaConsignado.vue') },
  // v18.14: saídas para outros procedimentos (mesma tela na farmácia e no almoxarifado)
  'comum/saidas_outros.html': { titulo: 'Saídas para outros procedimentos', componente: () => import('./SaidasOutros.vue') },
  'almoxarifado/reposicao_caixas.html': { titulo: 'Reposição das caixas', componente: () => import('./AlmoxarifadoReposicaoCaixas.vue') },
  'farmacia/caixa_saidas.html': { titulo: (d) => `Saídas da caixa ${d?.caixa?.id_caixa ?? ''}`, componente: () => import('./FarmaciaCaixaSaidas.vue') },
  'farmacia/caixa_consignado_etiqueta.html': { titulo: (d) => `Etiqueta ${d?.caixa?.id_caixa ?? ''}`, componente: () => import('./FarmaciaCaixaConsignadoEtiqueta.vue') },
  'farmacia/caixas_sala.html': { titulo: 'Caixas nas salas', componente: () => import('./FarmaciaCaixasSala.vue') },
  'farmacia/caixa_sala.html': { titulo: (d) => `Caixa ${d?.t?.id_caixa ?? ''}`, componente: () => import('./FarmaciaCaixaSala.vue') },
  'farmacia/devolucoes.html': { titulo: 'Não utilizados — dar ciência', componente: () => import('./FarmaciaDevolucoes.vue') },
  'farmacia/a_concluir.html': { titulo: 'Procedimentos a concluir', componente: () => import('./FarmaciaAConcluir.vue') },
  'farmacia/procedimento.html': { titulo: (d) => `Procedimento ${d?.atendimento?.prontuario ?? ''}`, componente: () => import('./FarmaciaProcedimento.vue') },
  'farmacia/atendimentos.html': { titulo: 'Dispensar para a sala', componente: () => import('./FarmaciaAtendimentos.vue') },
  'farmacia/estoque.html': { titulo: 'Estoque da farmácia', componente: () => import('./FarmaciaEstoque.vue') },
  'farmacia/recebimentos.html': { titulo: 'Receber do almoxarifado', componente: () => import('./FarmaciaRecebimentos.vue') },
  'farmacia/recebimento.html': { titulo: (d) => `Conferir envio ${d?.rem?.id_remessa ?? ''}`, componente: () => import('./FarmaciaRecebimento.vue') },
  'farmacia/solicitacoes.html': { titulo: 'Solicitações de OPME', componente: () => import('./FarmaciaSolicitacoes.vue') },
  'farmacia/solicitacao_imprimir.html': { titulo: 'Folha de separação', componente: () => import('./FarmaciaSolicitacaoImprimir.vue') },
  'farmacia/dispensacoes.html': { titulo: 'Dispensações', componente: () => import('./FarmaciaDispensacoes.vue') },
  'farmacia/usos_sem_dispensacao.html': { titulo: 'Usos sem dispensação', componente: () => import('./FarmaciaUsosSemDispensacao.vue') },
  'farmacia/conciliacao.html': { titulo: 'Conciliação por sala', componente: () => import('./FarmaciaConciliacao.vue') },

  // Sala de procedimento
  'sala_procedimento/hub.html': { titulo: 'Sala de procedimento', componente: () => import('./SalaHub.vue') },
  'sala_procedimento/caixas.html': { titulo: 'Caixas na sala', componente: () => import('./SalaCaixas.vue') },
  'sala_procedimento/atendimentos.html': { titulo: 'Atendimentos', componente: () => import('./SalaAtendimentos.vue') },
  'sala_procedimento/salas.html': { titulo: 'Salas', componente: () => import('./SalaSalas.vue') },
  'sala_procedimento/atendimento.html': { titulo: (d) => `Atendimento ${d?.atendimento?.prontuario ?? ''}`, componente: () => import('./SalaAtendimento.vue') },
  'sala_procedimento/concluir.html': { titulo: 'Finalizar registro de uso e devoluções', componente: () => import('./SalaConcluir.vue') },
  'sala_procedimento/correcao_uso.html': { titulo: 'Corrigir peça do uso', componente: () => import('./SalaCorrecaoUso.vue') },
  'sala_procedimento/estorno.html': { titulo: 'Estornar uso', componente: () => import('./SalaEstorno.vue') },
  'sala_procedimento/solicitacao.html': { titulo: (d) => `Solicitação de OPME · ${d?.atendimento?.prontuario ?? ''}`, componente: () => import('./SalaSolicitacao.vue') },
  'sala_procedimento/nao_cadastrado.html': { titulo: 'Material não cadastrado', componente: () => import('./SalaNaoCadastrado.vue') },
  'dispensacoes/confirmar.html': { titulo: 'Dispensação', componente: () => import('./DispensacaoConfirmar.vue') },
  'devolucoes/confirmar.html': { titulo: 'Confirmar devolução', componente: () => import('./DevolucaoConfirmar.vue') },
  'procedimentos/lista.html': { titulo: 'Procedimentos', componente: () => import('./Procedimentos.vue') },

  // Consignados
  'consignados/hub.html': { titulo: 'Consignados', componente: () => import('./ConsignadosHub.vue') },
  'consignados/pendentes.html': { titulo: 'Vincular a empenho', componente: () => import('./ConsignadosPendentes.vue') },
  'consignados/empenhos.html': { titulo: 'Empenhos', componente: () => import('./ConsignadosEmpenhos.vue') },
  'consignados/empenho.html': { titulo: (d) => `Empenho ${d?.empenho?.identificacao ?? ''}`, componente: () => import('./ConsignadosEmpenho.vue') },
  'consignados/associacoes.html': { titulo: 'Código consignado × AGHU', componente: () => import('./ConsignadosAssociacoes.vue') },
  'consignados/empenho_novo.html': { titulo: 'Novo empenho', componente: () => import('./ConsignadosEmpenhoNovo.vue') },

  // Consultas
  'consultas/hub.html': { titulo: 'Consultas', componente: () => import('./ConsultasHub.vue') },
  'consultas/itens.html': { titulo: 'Itens', componente: () => import('./ConsultasItens.vue') },
  'consultas/item.html': { titulo: (d) => d?.item?.xProd ?? 'Item', componente: () => import('./ConsultasItem.vue') },
  'consultas/lote.html': { titulo: 'Rastreio por lote', componente: () => import('./ConsultasLote.vue') },
  'consultas/validades.html': { titulo: 'Validades', componente: () => import('./ConsultasValidades.vue') },
  'consultas/caixa.html': { titulo: (d) => `Caixa ${d?.caixa?.id_caixa ?? ''}`, componente: () => import('./ConsultasCaixa.vue') },
  'consultas/utilizados.html': { titulo: 'Itens utilizados', componente: () => import('./ConsultasUtilizados.vue') },
  'consultas/recall.html': { titulo: 'Recall — bloqueio de lote', componente: () => import('./ConsultasRecall.vue') },
  'consultas/recall_detalhe.html': { titulo: (d) => `Lote ${d?.bloqueio?.nLote ?? ''}`, componente: () => import('./ConsultasRecallDetalhe.vue') },
  'consultas/dispensas.html': { titulo: 'Movimentações de dispensa', componente: () => import('./ConsultasDispensas.vue') },
  'consultas/eventos.html': { titulo: 'Histórico de movimentações', componente: () => import('./ConsultasEventos.vue') },
  'consultas/classificacao.html': { titulo: 'Por classificação', componente: () => import('./ConsultasClassificacao.vue') },
  'consultas/prontuario.html': { titulo: 'Prontuário', componente: () => import('./ConsultasProntuario.vue') },

  // Inventário
  'inventario/hub.html': { titulo: 'Inventário', componente: () => import('./InventarioHub.vue') },
  'inventario/contagem.html': { titulo: (d) => `Contagem ${d?.inv?.id_inventario ?? ''}`, componente: () => import('./InventarioContagem.vue') },
  'inventario/relatorio.html': { titulo: (d) => `Relatório ${d?.inventario?.id_inventario ?? ''}`, componente: () => import('./InventarioRelatorio.vue') },

  // v18.3: QG da enfermagem (chamados das salas)
  'qg/painel.html': { titulo: 'QG da enfermagem', componente: () => import('./QgEnfermagem.vue') },
  // v18.1: Central de monitoramento das salas
  'monitoramento/central.html': { titulo: 'Central das salas', componente: () => import('./MonitoramentoCentral.vue') },
  // Indicadores
  'indicadores/hub.html': { titulo: 'Indicadores', componente: () => import('./IndicadoresHub.vue') },
  'indicadores/fluxo.html': { titulo: 'Fluxo e gargalos', componente: () => import('./IndicadoresFluxo.vue') },
  'indicadores/desperdicio.html': { titulo: 'Desperdício e validade', componente: () => import('./IndicadoresDesperdicio.vue') },
  'indicadores/financeiro.html': { titulo: 'Financeiro e consumo', componente: () => import('./IndicadoresFinanceiro.vue') },
  'indicadores/qualidade.html': { titulo: 'Qualidade e conformidade', componente: () => import('./IndicadoresQualidade.vue') },
  'indicadores/metas.html': { titulo: 'Metas dos indicadores', componente: () => import('./IndicadoresMetas.vue') },

  // Administração
  'admin/chamados.html': { titulo: 'Chamados', componente: () => import('./AdminChamados.vue') },
  'admin/hub.html': { titulo: 'Administração', componente: () => import('./AdminHub.vue') },
  'admin/diagnostico.html': { titulo: 'Diagnóstico', componente: () => import('./AdminDiagnostico.vue') },
  'admin/entrega_paciente.html': { titulo: 'Entrega da caixa ao paciente', componente: () => import('./AdminEntregaPaciente.vue') },
};
