<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Entrada por nota fiscal</h1>
        <p>Importe o XML da NF-e.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/almoxarifado">Voltar</a></div>
    </div>

    <form method="post" action="/almoxarifado/nf" enctype="multipart/form-data" class="cartao">
      <div class="campo">
        <label class="obrigatorio">Arquivo XML da NF-e</label>
        <input type="file" name="arquivo" accept=".xml,text/xml" required>
        <div class="dica">Notas já importadas não são duplicadas — o sistema abre os itens pendentes.</div>
      </div>
      <button class="botao">Importar NF-e</button>
    </form>

    <div class="cartao" style="border-left:5px solid var(--azul)">
      <h2>Não tem o arquivo XML?</h2>
      <p>
        Com a chave de acesso da nota (os 44 números impressos no DANFE) dá para baixar o XML em
        <a href="https://meudanfe.com.br/" target="_blank" rel="noopener noreferrer">meudanfe.com.br</a>,
        e depois importar aqui.
      </p>
      <p class="suave pequeno" style="margin-bottom:0">
        É um site externo, sem relação com o hospital. Se o XML não estiver disponível lá, peça ao
        fornecedor — ou use o <a href="/almoxarifado/manual">cadastro manual</a>, que aceita o número
        da nota digitado.
      </p>
      <a class="botao secundario" href="https://meudanfe.com.br/" target="_blank" rel="noopener noreferrer"
         style="margin-top:.75rem">Abrir meudanfe.com.br</a>
    </div>

    <div class="cartao">
      <h2>Notas com itens pendentes</h2>
      <div v-if="d.notas?.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>NF</th><th>Fornecedor</th><th>Chave</th><th class="num">Pendentes</th><th></th></tr></thead>
          <tbody>
            <tr v-for="nota in d.notas" :key="nota.chave_nf">
              <td><strong>{{ nota.numero_nf }}</strong></td>
              <td>{{ nota.fornecedor }}</td>
              <td class="mono pequeno">{{ nota.chave_nf }}</td>
              <td class="num">{{ nota.pendentes }} de {{ nota.total }}</td>
              <td><a class="botao pequeno" :href="`/almoxarifado/nf/${nota.chave_nf}`">Abrir</a></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhuma nota com itens pendentes.</p>
    </div>

    <!-- nov/2026: entrada concluída no TraceOPME, falta lançar no AGHU -->
    <div v-if="d.a_lancar_aghu?.length" class="cartao" style="border-left:5px solid #b7791f;background:#fbf2e2">
      <h2>Falta lançar no AGHU ({{ d.a_lancar_aghu.length }})</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>NF</th><th>Fornecedor</th><th>Situação</th><th></th></tr></thead>
          <tbody>
            <tr v-for="n in d.a_lancar_aghu" :key="n.chave_nf">
              <td><strong>{{ n.numero_nf }}</strong></td>
              <td>{{ n.fornecedor }}</td>
              <td><span v-if="n.aghu_status === 'em_lancamento'" class="etiqueta azul">robô aberto</span>
                  <span v-else class="etiqueta amarelo">não lançada</span></td>
              <td><a class="botao pequeno" :href="`/almoxarifado/nf/${n.chave_nf}#aghu`">Lançar no AGHU</a></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ d: any }>();
</script>
