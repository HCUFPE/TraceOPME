<template>
  <div>
    <div class="cabecalho-pagina nao-imprimir">
      <div>
        <h1>Etiquetas QR</h1>
        <p>Para material que chegou sem código de barras. Imprima, recorte e cole na
           embalagem — a partir daí o item é bipado como qualquer outro.</p>
      </div>
      <div class="acoes">
        <button class="botao" type="button" @click="imprimir">Imprimir</button>
        <a class="botao secundario" :href="`${raiz}/manual`">Cadastrar outro</a>
        <a class="botao secundario" :href="raiz">Voltar</a>
      </div>
    </div>

    <div v-if="!d.qr_disponivel" class="aviso erro nao-imprimir">
      A biblioteca de QR Code não está instalada no servidor. Peça à TI para instalar as
      dependências (requirements.txt). Enquanto isso, o código abaixo pode ser digitado à mão na tela de bipagem.
    </div>

    <form method="get" :action="`${raiz}/etiquetas`" class="cartao nao-imprimir">
      <div class="filtros">
        <div class="campo">
          <label>Buscar por código, produto ou lote</label>
          <input type="text" name="busca" :defaultValue="d.busca" placeholder="ex.: OPME ou parafuso">
        </div>
        <button class="botao secundario">Buscar</button>
      </div>
      <p class="suave pequeno" style="margin:.6rem 0 0">
        Serve também para reimprimir uma etiqueta perdida: busque o código e imprima de novo.
      </p>
    </form>

    <template v-if="d.itens?.length">
      <div class="cartao nao-imprimir" style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap">
        <strong>{{ d.itens.length }} etiqueta(s)</strong>
        <span class="pequeno">Tamanho:</span>
        <a :class="['botao', 'pequeno', d.tamanho === 'pequena' ? '' : 'secundario']" :href="`${base}&tamanho=pequena`">Pequena (5 × 2,5 cm)</a>
        <a :class="['botao', 'pequeno', d.tamanho === 'media' ? '' : 'secundario']" :href="`${base}&tamanho=media`">Média (7 × 3,5 cm)</a>
        <span class="pequeno suave">Na impressão, use escala 100% (sem “ajustar à página”).</span>
      </div>
      <div :class="['folha-etiquetas', `tam-${d.tamanho}`]">
        <div v-for="(item, i) in d.itens" :key="item.id_unidade || i" class="etq">
          <ImagemApi v-if="d.qr_disponivel" class="etq-qr"
                     :src="`${raiz}/qr/${encodeURIComponent(item.codigo_barras)}.png?sem_legenda=1`"
                     :alt="`QR ${item.codigo_barras}`" />
          <div class="etq-txt">
            <div class="etq-cod">{{ item.codigo_barras }}</div>
            <div class="etq-desc">{{ item.descritivo_hospital || item.xProd }}</div>
            <div class="etq-info">AGHU {{ item.codigo_aghu || '—' }} · L {{ item.nLote || '—' }}<br>
              Val. {{ f.dataBr(item.dVal) || '—' }}<template v-if="item.numero_serie"> · S {{ item.numero_serie }}</template></div>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="cartao">
      <p class="vazio">
        <template v-if="d.codigo || d.busca">Nenhum item encontrado. Confira o código ou busque pela descrição.</template>
        <template v-else>
          Busque um código acima, ou cadastre um material marcando
          <strong>“item sem código de barras”</strong> em
          <a :href="`${raiz}/manual`">Cadastro manual</a>.
        </template>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import ImagemApi from '../../components/opme/ImagemApi.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const raiz = computed(() => props.d.base || '/almoxarifado');
const base = computed(() =>
  `${raiz.value}/etiquetas?codigo=${encodeURIComponent(props.d.codigo || '')}&busca=${encodeURIComponent(props.d.busca || '')}`);

function imprimir() {
  window.print();
}
</script>

<style>
.folha-etiquetas { display: flex; flex-wrap: wrap; gap: 3mm; background: #fff; padding: 4mm; border-radius: 8px; }
.etq { display: flex; align-items: center; gap: 1.5mm; box-sizing: border-box; overflow: hidden;
       border: 1px dashed #999; background: #fff; color: #000; padding: 1mm 1.5mm; break-inside: avoid; page-break-inside: avoid; }
.etq-qr { flex: 0 0 auto; image-rendering: pixelated; }
.etq-txt { min-width: 0; line-height: 1.12; }
.etq-cod { font-family: monospace; font-weight: 700; word-break: break-all; }
.etq-desc { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-weight: 600; }
/* pequena: 5 × 2,5 cm */
.tam-pequena .etq { width: 50mm; height: 25mm; }
.tam-pequena .etq-qr { width: 21mm; height: 21mm; }
.tam-pequena .etq-cod { font-size: 6.5pt; }
.tam-pequena .etq-desc { font-size: 5.5pt; margin: .4mm 0; }
.tam-pequena .etq-info { font-size: 5.5pt; }
/* média: 7 × 3,5 cm */
.tam-media .etq { width: 70mm; height: 35mm; }
.tam-media .etq-qr { width: 30mm; height: 30mm; }
.tam-media .etq-cod { font-size: 8pt; }
.tam-media .etq-desc { font-size: 7pt; margin: .6mm 0; }
.tam-media .etq-info { font-size: 7pt; }
@page { margin: 8mm; }
@media print {
  .folha-etiquetas { padding: 0; gap: 2mm; }
}
</style>
