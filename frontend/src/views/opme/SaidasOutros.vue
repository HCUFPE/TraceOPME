<script setup lang="ts">
/** v18.14 — Saídas de OPME para outros procedimentos (farmácia e almoxarifado). */
const props = defineProps<{ d: any }>()
const d = props.d
</script>

<template>
  <div class="pagina">
    <p class="migalhas"><a :href="d.base">{{ d.base_modulo === 'almoxarifado' ? 'Almoxarifado' : 'Farmácia' }}</a>
      › Saídas para outros procedimentos</p>
    <div class="cab-pagina">
      <h1>Saídas para outros procedimentos</h1>
      <a class="botao" :href="`/bipagem/${d.operacao}`">Dispensar para outro procedimento</a>
    </div>
    <p class="pequeno suave" style="margin:.2rem 0 1rem">Material que saiu do estoque
      {{ d.base_modulo === 'almoxarifado' ? 'do almoxarifado' : 'da farmácia' }} para um procedimento fora do fluxo
      de sala/paciente. O uso nesses lugares não é acompanhado item a item aqui — fica o registro de quem retirou,
      para onde foi e a justificativa.</p>

    <form method="get" :action="`${d.base}/saidas-outros`" class="filtros">
      <div class="campo"><label for="de">De</label>
        <input type="date" id="de" name="de" :defaultValue="d.de"></div>
      <div class="campo"><label for="ate">Até</label>
        <input type="date" id="ate" name="ate" :defaultValue="d.ate"></div>
      <div class="campo"><label for="destino">Destino</label>
        <input type="text" id="destino" name="destino" list="destinos-saida" :defaultValue="d.destino"
               placeholder="todos" style="width:17rem">
        <datalist id="destinos-saida">
          <option v-for="x in d.destinos" :key="x" :value="x"></option>
        </datalist></div>
      <button class="botao secundario">Filtrar</button>
    </form>

    <p v-if="!d.linhas.length" class="vazio">Nenhuma saída para outros procedimentos neste período.</p>

    <template v-else>
      <div class="cartao" style="margin:.8rem 0">
        <h3 style="margin:0 0 .4rem">{{ d.total_itens }} item(ns) no período</h3>
        <table class="tabela compacta">
          <thead><tr><th>Destino / procedimento</th><th class="num">Itens</th><th class="num">Materiais</th></tr></thead>
          <tbody>
            <tr v-for="r in d.resumo" :key="r.destino">
              <td>{{ r.destino }}</td><td class="num">{{ r.itens }}</td><td class="num">{{ r.materiais }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <table class="tabela">
        <thead>
          <tr>
            <th>Data</th><th>Material</th><th>Lote / validade</th><th>Destino</th>
            <th>Retirou</th><th>Observação</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in d.linhas" :key="l.id_unidade + l.data_evento" :class="{ desfeita: l.desfeita }">
            <td class="mono">{{ l.data_br }}<br><span class="pequeno suave">{{ l.hora }} · {{ l.origem }}</span></td>
            <td><a :href="`/consultas/item/${l.id_unidade}`">{{ l.material }}</a>
              <br><span class="pequeno suave">AGHU {{ l.codigo_aghu || '—' }}</span></td>
            <td class="mono pequeno">{{ l.nLote || '—' }}<br><span class="suave">{{ l.validade_br }}</span></td>
            <td>{{ l.destino }}
              <span v-if="l.desfeita" class="etiqueta cinza">saída desfeita — item voltou ao estoque</span></td>
            <td class="pequeno">{{ l.usuario }}</td>
            <td class="pequeno suave">{{ l.observacao || '—' }}</td>
            <td>
              <details v-if="!l.desfeita" class="desfazer">
                <summary class="pequeno">Bipado por engano?</summary>
                <form method="post" :action="`${d.base}/saidas-outros/${l.id_unidade}/desfazer`"
                      class="linha-botoes" style="margin-top:.3rem;align-items:center"
                      data-confirmar="Desfazer esta saída? O item volta para o estoque de onde saiu.">
                  <input type="text" name="motivo" required placeholder="motivo" style="width:11rem">
                  <button class="botao secundario pequeno">Desfazer</button>
                </form>
              </details>
            </td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<style scoped>
.cab-pagina { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
.cab-pagina h1 { flex: 1 1 auto; margin: 0; }
.filtros { display: flex; gap: .8rem; align-items: flex-end; flex-wrap: wrap; }
.num { text-align: right; }
tr.desfeita td { opacity: .55; text-decoration: line-through; }
tr.desfeita .etiqueta { text-decoration: none; }
</style>
