<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>{{ naFarmacia ? 'Cadastro manual na farmácia' : 'Cadastro manual de material' }}</h1>
        <p v-if="naFarmacia">O material cadastrado aqui entra <strong>direto no estoque da farmácia escolhida</strong>
          (Bloco Cirúrgico ou Hemodinâmica), sem passar pelo almoxarifado.</p>
        <p v-else>Use para consignados, doações, empréstimos e itens sem XML de NF-e.</p>
      </div>
      <div class="acoes"><a class="botao secundario" :href="base">Voltar</a></div>
    </div>

    <!-- nov/2026: o leitor de código de barras manda Enter depois do código; aqui o
         Enter só passa para o próximo campo — o cadastro só sai pelo botão. -->
    <form ref="formulario" method="post" :action="`${base}/manual`" class="cartao" style="max-width:900px"
          @keydown.enter="aoEnter">
      <!-- nov/2026: na farmácia, escolher o estoque de destino. -->
      <div v-if="naFarmacia" class="campo" id="campo-farmacia" style="max-width:420px">
        <label class="obrigatorio" for="manual-farmacia">Estoque de destino</label>
        <select id="manual-farmacia" name="farmacia" required>
          <option value="">— escolha a farmácia —</option>
          <option v-for="(rotulo, chave) in d.farmacias" :key="chave" :value="chave"
                  :selected="chave === (v.farmacia || d.farmacia_atual)">{{ rotulo }}</option>
        </select>
      </div>
      <div class="grade grade-2">
        <div class="campo">
          <label class="obrigatorio">Descrição do produto</label>
          <input type="text" name="xProd" :defaultValue="v.xProd || ''" required>
        </div>
        <div class="campo">
          <label class="obrigatorio">Código de barras</label>
          <input type="text" id="codigo-barras" name="codigo_barras" v-model="codigoBarras"
                 :disabled="semCodigo" :required="!semCodigo"
                 :placeholder="semCodigo ? 'gerado automaticamente ao salvar' : ''">
          <div class="dica">Pode bipar direto neste campo.</div>
          <label class="pequeno" style="display:flex;gap:.4rem;align-items:center;font-weight:400;margin-top:.5rem">
            <input type="checkbox" id="sem-codigo" name="sem_codigo_barras" value="1" style="width:auto" v-model="semCodigo">
            Item <strong>sem código de barras</strong> — gerar um código interno e etiqueta QR
          </label>
          <div v-if="semCodigo" class="dica" id="dica-qr">
            O código é montado como <span class="mono">CÓDIGO AGHU(LOTE)</span> — preencha
            esses dois campos abaixo. A etiqueta abre para imprimir logo após salvar;
            cole na embalagem antes de guardar o material.
          </div>
        </div>
        <div class="campo">
          <label class="obrigatorio">Código AGHU</label>
          <input type="text" id="codigo-aghu" name="codigo_aghu" v-model="aghu" required>
          <DescritivoHc :codigo="aghu" />
        </div>
        <div class="campo">
          <label class="obrigatorio">Fornecedor</label>
          <input type="text" name="fornecedor" :defaultValue="v.fornecedor || ''" required>
        </div>
        <div class="campo">
          <label class="obrigatorio">Marca / Fabricante</label>
          <input type="text" name="marca_fabricante" :defaultValue="v.marca_fabricante || ''" required>
        </div>
        <div class="campo">
          <label class="obrigatorio">Lote</label>
          <input type="text" name="nLote" :defaultValue="v.nLote || ''" required>
        </div>
        <div class="campo">
          <label>Fabricação</label>
          <input type="date" name="dFab" :defaultValue="v.dFab || ''">
        </div>
        <div class="campo">
          <label class="obrigatorio">Validade</label>
          <input type="date" name="dVal" required :min="hoje" :defaultValue="v.dVal || ''">
        </div>
        <div class="campo">
          <label class="obrigatorio">Quantidade</label>
          <input type="number" name="quantidade" min="1" max="500" :defaultValue="v.quantidade || ''" required
                 inputmode="numeric" placeholder="quantas unidades?">
          <div class="dica">Obrigatória — conte as unidades. Cada uma recebe um identificador próprio para rastreio individual.</div>
        </div>
        <div class="campo">
          <label>Valor unitário</label>
          <input type="text" name="vUnCom" :defaultValue="v.vUnCom || ''" placeholder="0,00">
        </div>
        <div class="campo">
          <label>Classificação</label>
          <select name="tipo_entrada" v-model="tipo">
            <option v-for="(nome, codigo) in d.tipos" :key="codigo" :value="codigo">{{ nome }}</option>
          </select>
        </div>
        <div v-if="tipo === 'consignado'" class="campo">
          <label>Código consignado</label>
          <CampoCodigoConsignado :aghu="aghu" :inicial="v.codigo_consignado || ''" :base="base" />
        </div>
        <div class="campo">
          <label>Número da NF <span class="opcional">(se houver)</span></label>
          <input type="text" name="numero_nf" :defaultValue="v.numero_nf || ''">
        </div>
      </div>

      <div class="campo">
        <label>Números de série <span class="opcional">(um por linha, opcional)</span></label>
        <textarea name="numeros_serie" rows="3" :defaultValue="v.numeros_serie || ''"></textarea>
      </div>

      <div class="linha-botoes">
        <button class="botao">Cadastrar unidades</button>
        <a class="botao secundario" :href="`${base}/etiquetas`">Reimprimir etiqueta</a>
        <a class="botao secundario" :href="base">Cancelar</a>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import CampoCodigoConsignado from '../../components/opme/CampoCodigoConsignado.vue';
import DescritivoHc from '../../components/opme/DescritivoHc.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
useTela();
// nov/2026: o calendário não deixa escolher validade anterior a hoje.
const hoje = (() => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); })();
// Quando o cadastro é recusado, a tela volta com o que foi digitado (`valores`).
const v = computed(() => props.d.valores || {});
// nov/2026: a mesma tela serve ao almoxarifado e às farmácias (d.base = "/farmacia").
const base = computed(() => props.d.base || '/almoxarifado');
const naFarmacia = computed(() => base.value === '/farmacia');
const aghu = ref(v.value.codigo_aghu || '');
const codigoBarras = ref(v.value.codigo_barras || '');
const semCodigo = ref(!!v.value.sem_codigo_barras);
const tipo = ref(v.value.tipo_entrada || 'aquisicao_propria');
const formulario = ref<HTMLFormElement | null>(null);

/** Enter (do leitor ou do teclado) leva ao próximo campo, sem enviar o formulário. */
function aoEnter(e: KeyboardEvent) {
  const alvo = e.target as HTMLElement;
  if (!alvo || alvo.tagName === 'TEXTAREA' || alvo.tagName === 'BUTTON' || alvo.tagName === 'A') return;
  e.preventDefault();
  const campos = Array.from(formulario.value?.querySelectorAll<HTMLElement>(
    'input:not([type=hidden]):not([type=checkbox]):not([disabled]), select, textarea') || [])
    .filter((c) => c.offsetParent !== null);
  const proximo = campos[campos.indexOf(alvo) + 1];
  proximo?.focus();
}
// Com o código gerado pelo sistema, o campo deixa de ser obrigatório —
// e fica desabilitado para não sobrar um valor digitado por engano.
watch(semCodigo, (marcado) => { if (marcado) codigoBarras.value = ''; });
</script>
