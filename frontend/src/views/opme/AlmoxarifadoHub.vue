<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Almoxarifado</h1>
      </div>
    </div>

    <div v-if="d.alertas?.length" class="cartao" style="margin-bottom:1.25rem;border-left:5px solid var(--vermelho)">
      <h2>{{ d.alertas.length }} alerta(s) do almoxarifado</h2>
      <p class="suave pequeno">Confira com atenção redobrada.</p>
      <div v-for="a in d.alertas" :key="a.id_alerta" style="padding:.6rem 0;border-bottom:1px solid var(--borda)">
        <p class="pequeno mono" style="margin:0;white-space:pre-wrap">{{ a.mensagem }}</p>
        <div v-if="a.itens?.length" class="pequeno" style="margin:.3rem 0">
          Abrir cada item:
          <template v-for="(item, i) in a.itens" :key="item.id_unidade">
            <a :href="`/consultas/item/${item.id_unidade}`">{{ item.codigo_aghu || item.xProd }}</a><template v-if="i < a.itens.length - 1"> ·</template>
          </template>
        </div>
        <div v-else-if="a.link" class="pequeno" style="margin:.3rem 0"><a :href="a.link">Abrir</a></div>
        <span class="suave pequeno">{{ f.dataHoraBr(a.criado_em) }}</span>
        <form method="post" :action="`/alertas/${a.id_alerta}/resolver`" style="display:inline;margin-left:.5rem">
          <button class="botao secundario pequeno">Marcar como resolvido</button>
        </form>
      </div>
    </div>

    <div v-if="d.nao_cadastrados" class="linha-cartoes">
      <a v-if="d.nao_cadastrados" class="acao-card alta" href="/almoxarifado/nao-cadastrados">
        <h3>Material não cadastrado usado na sala</h3>
        <div class="numero">{{ d.nao_cadastrados }}</div>
        <p class="rotulo">Completar o cadastro do que a sala usou.</p>
      </a>
    </div>
    <!-- v18.16: faixas com nome, uma cor por faixa e grade que se ajusta (sem cartão órfão) -->
    <section class="faixa-acoes">
      <h2>Entrada e cadastro</h2>
      <div class="linha-cartoes cinco">
        <a class="acao-card cor-verde" href="/almoxarifado/nf">
          <h3>Dar entrada por nota fiscal</h3>
          <p class="rotulo">Importar o XML da NF-e.</p>
          <span v-if="d.notas?.length" class="etiqueta amarelo">{{ d.notas.length }} NF com item pendente</span>
          <span v-if="d.a_lancar_aghu" class="etiqueta vermelho">{{ d.a_lancar_aghu }} NF falta lançar no AGHU</span>
        </a>
        <a class="acao-card cor-verde" href="/almoxarifado/manual">
          <h3>Cadastro manual</h3>
          <p class="rotulo">Consignado, doação ou item sem XML.</p>
        </a>
        <a :class="['acao-card', 'cor-verde', { alta: d.pendentes_planilha }]" href="/almoxarifado/planilha">
          <h3>Planilha de lotes do AGHU</h3>
          <div v-if="d.pendentes_planilha" class="numero">{{ d.pendentes_planilha }}</div>
          <p class="rotulo">Importar a planilha de lotes.</p>
        </a>
        <a class="acao-card cor-verde" href="/almoxarifado/correcoes">
          <h3>Corrigir cadastro</h3>
          <p class="rotulo">Lote, validade, fornecedor, código.</p>
        </a>
        <a class="acao-card cor-verde" href="/almoxarifado/etiquetas">
          <h3>Etiquetas QR</h3>
          <p class="rotulo">Itens sem código de barras.</p>
        </a>
      </div>
    </section>

    <section class="faixa-acoes">
      <h2>Com as farmácias e caixas de consignado</h2>
      <div class="linha-cartoes">
        <a :class="['acao-card', 'cor-marinho', { alta: d.envios_pendencias }]" href="/almoxarifado/envios">
          <h3>Enviar para a farmácia</h3>
          <div v-if="d.envios_pendencias" class="numero">{{ d.envios_pendencias }}</div>
          <p class="rotulo">Bloco ou Hemodinâmica.
            <template v-if="d.envios_aguardando"><br><span class="etiqueta amarelo">{{ d.envios_aguardando }} envio(s) aguardando a farmácia</span></template>
            <template v-if="d.envios_pendencias"><br><span class="etiqueta vermelho">{{ d.envios_pendencias }} item(ns) não recebido(s) — tratar</span></template></p>
        </a>
        <a :class="['acao-card', 'cor-marinho', { alta: d.devolucoes_farmacia || d.devolucoes_farmacia_pendencias }]" href="/almoxarifado/devolucoes-farmacia">
          <h3>Devoluções das farmácias</h3>
          <div v-if="d.devolucoes_farmacia" class="numero">{{ d.devolucoes_farmacia }}</div>
          <p class="rotulo">Conferir e dar ciência.
            <template v-if="d.devolucoes_farmacia_pendencias"><br><span class="etiqueta vermelho">{{ d.devolucoes_farmacia_pendencias }} item(ns) não recebido(s)</span></template></p>
        </a>
        <a class="acao-card cor-roxo" href="/almoxarifado/caixas">
          <h3>Caixas de consignado</h3>
          <div v-if="d.caixas_a_caminho" class="numero">{{ d.caixas_a_caminho }}</div>
          <p class="rotulo">Montar e enviar caixas.
            <template v-if="d.caixas_a_caminho"><br><span class="pequeno">caixa(s) aguardando a ciência da farmácia</span></template></p>
        </a>
        <a class="acao-card cor-roxo" href="/almoxarifado/reposicao-caixas">
          <h3>Reposição das caixas</h3>
          <p class="rotulo"><template v-if="d.a_repor_caixas"><strong>{{ d.a_repor_caixas }}</strong> unidade(s) a repor</template>
            <template v-else>Nada a repor (últimos 30 dias).</template></p>
        </a>
      </div>
    </section>

    <section class="faixa-acoes">
      <h2>Saídas e fornecedor</h2>
      <div class="linha-cartoes">
        <a class="acao-card cor-amarelo" href="/almoxarifado/saidas-outros">
          <h3>Outros procedimentos</h3>
          <p class="rotulo">Dispensar fora do fluxo de sala/paciente e ver as saídas.</p>
        </a>
        <a class="acao-card cor-amarelo" href="/bipagem/devolver_fornecedor">
          <h3>Devolver ao fornecedor</h3>
          <p class="rotulo">Saída para o fornecedor.</p>
        </a>
        <a class="acao-card cor-amarelo" href="/almoxarifado/romaneios-fornecedor">
          <h3>Romaneio de devolução</h3>
          <p class="rotulo">PDF para assinatura.</p>
        </a>
      </div>
    </section>

    <section class="faixa-acoes">
      <h2>Consultas e relatórios</h2>
      <div class="linha-cartoes">
        <a class="acao-card cor-azul" href="/consultas/itens?status=em_estoque_recebimento">
          <h3>Estoque do almoxarifado</h3>
          <div class="numero">{{ d.em_estoque }}</div>
          <p class="rotulo">unidade(s) no almoxarifado</p>
        </a>
        <a class="acao-card cor-azul" href="/consultas/dispensas?tipo=envios">
          <h3>Relatório de dispensas</h3>
          <p class="rotulo">Por período. Planilha e PDF.</p>
        </a>
      </div>
    </section>

    <div v-if="d.notas?.length" class="cartao" style="margin-top:1.5rem">
      <h2>Notas com itens pendentes de entrada</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>NF</th><th>Fornecedor</th><th>Importada em</th><th class="num">Pendentes</th><th></th></tr></thead>
          <tbody>
            <tr v-for="nota in d.notas" :key="nota.chave_nf">
              <td><strong>{{ nota.numero_nf }}</strong></td>
              <td>{{ nota.fornecedor }}</td>
              <td class="pequeno">{{ f.dataHoraBr(nota.data_importacao) }}</td>
              <td class="num">{{ nota.pendentes }} de {{ nota.total }}</td>
              <td><a class="botao pequeno" :href="`/almoxarifado/nf/${nota.chave_nf}`">Dar entrada</a></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
