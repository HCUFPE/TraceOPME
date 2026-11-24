<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Estoque da {{ d.farmacias[d.farmacia] }}</h1>
        <p>O que a farmácia tem para dispensar à sala, por material, lote e validade. Só entra aqui o que
           a farmácia recebeu do almoxarifado e deu ciência.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>

    <div class="linha-botoes" style="margin-bottom:1rem">
      <a v-for="(nome, chave) in d.farmacias" :key="chave" :class="['botao', chave === d.farmacia ? '' : 'secundario']"
         :href="`/farmacia/estoque?farmacia=${encodeURIComponent(String(chave))}`">{{ nome }} ({{ d.por_farmacia[chave] }})</a>
    </div>

    <form method="get" action="/farmacia/estoque" class="cartao">
      <input type="hidden" name="farmacia" :value="d.farmacia">
      <div class="filtros">
        <div class="campo" style="flex:1">
          <label>Buscar</label>
          <input type="text" name="busca" :defaultValue="d.busca" placeholder="código AGHU, descrição, lote, código de barras ou fornecedor">
        </div>
        <button class="botao">Buscar</button>
      </div>
    </form>

    <div class="cartao">
      <div class="entre">
        <h2>{{ d.total }} unidade(s) em estoque<template v-if="d.busca"> para “{{ d.busca }}”</template></h2>
        <a v-if="d.a_caminho" class="pequeno" href="/farmacia/recebimentos">+ {{ d.a_caminho }} a caminho (aguardando ciência)</a>
      </div>
      <!-- v18.23: a etiqueta tem lote, mas esse lote não está nesta farmácia.
           Antes a tela mostrava outros lotes do mesmo produto sem avisar. -->
      <div v-if="d.aviso_lote" class="aviso alerta" style="margin:.2rem 0 .8rem">
        <strong>{{ d.aviso_lote }}</strong>
        <template v-if="d.onde_esta?.length">
          <br>Esse lote está hoje em:
          <span v-for="(o, n) in d.onde_esta" :key="n">{{ n ? ' · ' : ' ' }}<strong>{{ o.quantidade }}</strong> {{ o.rotulo }}</span>.
          <br><span class="pequeno">Se precisa dele na farmácia, peça ao almoxarifado o envio e dê ciência no recebimento.</span>
        </template>
      </div>
      <div v-if="d.linhas.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>AGHU</th><th>Material</th><th>Lote</th><th>Validade</th><th>Fornecedor / marca</th><th class="num">Qtd.</th></tr></thead>
          <tbody>
            <tr v-for="(l, n) in d.linhas" :key="n">
              <td class="mono">{{ l.codigo_aghu || '—' }}</td>
              <td>{{ l.xProd }}<br><span class="mono pequeno suave">{{ l.codigo_barras || '' }}</span></td>
              <td class="mono">{{ l.nLote || '—' }}</td>
              <td>{{ f.dataBr(l.dVal) || '—' }}</td>
              <td class="pequeno">{{ l.fornecedor || '—' }}<template v-if="l.marca_fabricante"><br><span class="suave">{{ l.marca_fabricante }}</span></template></td>
              <td class="num"><strong>{{ l.quantidade }}</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum material no estoque desta farmácia<template v-if="d.busca"> para essa busca</template>.
        O material entra aqui quando a farmácia dá ciência de um envio do almoxarifado.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
