<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Receber material</h1>
        <p>Envios do almoxarifado e transferências da outra farmácia para esta. Confira (pela lista ou bipando) e dê ciência: o que você
           receber entra no estoque da farmácia e passa a poder ser dispensado para a sala.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/farmacia">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />
    <p class="pequeno" style="margin:.2rem 0 .8rem">
      <template v-if="d.filtrando">Mostrando só {{ f.rotuloUnidade(d.unidade_atual) }} · <a href="/farmacia/recebimentos?todas=1">ver de todas as farmácias</a></template>
      <template v-else>Mostrando todas as farmácias.</template>
    </p>

    <div class="cartao" style="border-left:5px solid var(--amarelo, #b58100)">
      <h2>Para conferir ({{ d.enviadas.length }})</h2>
      <div v-if="d.enviadas.length" class="tabela-rolagem"><table>
        <thead><tr><th>Envio</th><th>De</th><th>Para</th><th class="num">Itens</th><th>Enviado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in d.enviadas" :key="r.id_remessa">
            <td class="mono pequeno">{{ r.id_remessa }}</td><td><span :class="['etiqueta', r.sentido === 'farmacia_farmacia' ? 'azul' : 'cinza']">{{ r.de }}</span></td><td>{{ r.farmacia_rotulo }}</td><td class="num">{{ r.qtd }}</td>
            <td class="pequeno">{{ r.enviada_por }} · {{ f.dataHoraBr(r.enviada_em) }}<template v-if="r.observacao"><br><span class="suave">{{ r.observacao }}</span></template></td>
            <td><a class="botao pequeno" :href="`/farmacia/recebimento/${r.id_remessa}`">Conferir e dar ciência</a></td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhum envio aguardando conferência.</p>
    </div>

    <div v-if="d.pendencias?.length" class="cartao" style="border-left:5px solid var(--vermelho, #b3261e)">
      <h2>Não recebidos — pendências ({{ d.pendencias.length }})</h2>
      <p class="pequeno suave">Itens enviados (pelo almoxarifado ou pela outra farmácia) que não foram recebidos na conferência. Se chegou depois, marque
        “recebi”. Se não chegou, quem enviou registra a tratativa (voltou à origem ou divergência).</p>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Envio</th><th>De</th><th>Material</th><th>AGHU</th><th>Lote</th><th>Validade</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in d.pendencias" :key="p.id_item">
            <td class="mono pequeno">{{ p.id_remessa }}</td><td class="pequeno">{{ p.de }}</td><td class="pequeno">{{ p.descricao }}</td>
            <td class="mono pequeno">{{ p.codigo_aghu || '—' }}</td><td class="mono pequeno">{{ p.nLote || '—' }}</td>
            <td class="pequeno">{{ p.validade }}</td>
            <td><form method="post" :action="`/farmacia/recebimento/item/${p.id_item}/recebi`" style="margin:0"
                      data-confirmar="Confirmar que este item chegou na farmácia?">
              <button class="botao secundario pequeno">recebi</button></form></td>
          </tr>
        </tbody>
      </table></div>
    </div>

    <div v-if="d.conferidas?.length" class="cartao">
      <h2>Conferidos recentemente</h2>
      <ul class="pequeno lista" style="margin:0 0 0 1rem">
        <li v-for="r in d.conferidas" :key="r.id_remessa"><a :href="`/farmacia/recebimento/${r.id_remessa}`" class="mono">{{ r.id_remessa }}</a> · {{ r.de }} → {{ r.farmacia_rotulo }} ·
          {{ r.qtd }} item(ns) · ciência de {{ r.conferida_nome }} em {{ f.dataHoraBr(r.conferida_em) }}
          <span v-if="r.nao_recebidos" class="etiqueta vermelho">{{ r.nao_recebidos }} não recebido(s)</span></li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
