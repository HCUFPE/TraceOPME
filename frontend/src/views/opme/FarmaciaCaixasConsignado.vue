<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Caixas de consignado</h1>
        <p v-if="almox">Monte a caixa no almoxarifado bipando os itens do estoque e dispense para a farmácia.
           A farmácia dá ciência ao receber e, dali em diante, completa a caixa e envia para as salas.</p>
        <p v-else>Monte a caixa bipando cada item para dentro. Na sala, o uso é bipado por item; na
           devolução, a sala bipa só a caixa e digita quantos itens voltaram.</p>
      </div>
      <div class="acoes"><a class="botao secundario" :href="almox ? '/almoxarifado' : '/farmacia'">Voltar</a></div>
    </div>


    <div v-if="!almox && d.chegando?.length" class="cartao" style="border-left:4px solid #b7791f;background:#fffaf0">
      <h2>Chegando do almoxarifado — dar ciência</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Código</th><th>Nome</th><th>Fornecedores dos itens</th><th class="num">Itens</th><th>Dispensada em</th><th></th></tr></thead>
          <tbody>
            <tr v-for="c in d.chegando" :key="c.id_caixa">
              <td class="mono"><strong>{{ c.id_caixa }}</strong></td><td>{{ c.nome }}</td><td>{{ c.fornecedores || '—' }}</td>
              <td class="num">{{ c.total }}</td><td class="pequeno">{{ f.dataHoraBr(c.enviada_em) }} · {{ c.enviada_por }}</td>
              <td style="display:flex;gap:.4rem">
                <a class="botao secundario pequeno" :href="`${base}/${c.id_caixa}`">Ver</a>
                <form method="post" :action="`${base}/${c.id_caixa}/receber`" style="margin:0"
                      :data-confirmar="`Confirmar que a caixa ${c.id_caixa} chegou na farmácia?`">
                  <button class="botao pequeno">Dar ciência</button></form>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="cartao">
      <h2>{{ d.caixas.length }} caixa(s){{ almox ? ' no almoxarifado ou a caminho' : '' }}</h2>
      <div v-if="d.caixas.length" class="tabela-rolagem">
        <table>
          <thead><tr><th>Código</th><th>Nome</th><th>Fornecedores dos itens</th><th class="num">Itens dentro</th><th v-if="almox">Onde está</th><th>Situação</th><th></th></tr></thead>
          <tbody>
            <tr v-for="c in d.caixas" :key="c.id_caixa">
              <td class="mono"><strong>{{ c.id_caixa }}</strong></td>
              <td>{{ c.nome }}</td>
              <td>{{ c.fornecedores || '—' }}</td>
              <td class="num">{{ c.total }}</td>
              <td v-if="almox">
                <span v-if="c.local === 'transito'" class="etiqueta amarelo">a caminho · {{ d.farmacias?.[c.farmacia] || c.farmacia }}</span>
                <span v-else class="etiqueta azul">no almoxarifado</span>
              </td>
              <td>
                <template v-if="c.bloqueada">
                  <span class="etiqueta vermelho">BLOQUEADA — conferir</span>
                  <br><span class="suave pequeno">{{ c.bloqueio_motivo }}</span>
                </template>
                <span v-else class="etiqueta verde">liberada</span>
              </td>
              <td style="white-space:nowrap">
                <a :class="['botao', 'pequeno', c.bloqueada ? '' : 'secundario']" :href="`${base}/${c.id_caixa}?abrir=1`">{{ c.bloqueada ? 'Conferir' : 'Abrir' }}</a>
                <a class="botao secundario pequeno" style="margin-left:.3rem" :href="`${base}/${c.id_caixa}/saidas`">Saídas</a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhuma caixa ainda. Crie a primeira abaixo.</p>
    </div>

    <div v-if="almox && d.nas_farmacias?.length" class="cartao">
      <h2>Já entregues às farmácias</h2>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Código</th><th>Nome</th><th>Farmácia</th><th class="num">Itens</th><th>Ciência em</th><th></th></tr></thead>
          <tbody>
            <tr v-for="c in d.nas_farmacias" :key="c.id_caixa">
              <td class="mono">{{ c.id_caixa }}</td><td>{{ c.nome }}</td><td>{{ d.farmacias?.[c.farmacia] || c.farmacia || '—' }}</td>
              <td class="num">{{ c.total }}</td><td class="pequeno">{{ f.dataHoraBr(c.recebida_em) }} · {{ c.recebida_nome || c.recebida_por }}</td>
              <td><a class="botao secundario pequeno" :href="`${base}/${c.id_caixa}`">Ver</a></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <form method="post" :action="base" class="cartao">
      <h2>Nova caixa de consignado</h2>
      <div class="campo" style="max-width:560px"><label class="obrigatorio">Nome da caixa</label>
        <input type="text" name="nome" required placeholder="Ex.: CARDIOLOGIA - NID"></div>
      <p class="suave pequeno">O código sai do nome (ex.: CX-CARD-01). Os itens podem ser de fornecedores diferentes.
         Depois de criar, imprima a etiqueta e bipe os itens para dentro.</p>
      <button class="botao">Criar caixa</button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const almox = computed(() => props.d.modo === 'almoxarifado');
const base = computed(() => props.d.base || '/farmacia/caixas-consignado');

</script>
