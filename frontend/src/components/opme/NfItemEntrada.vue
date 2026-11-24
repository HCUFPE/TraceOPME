<template>
  <div class="cartao" :style="estiloValidade(item)">
    <div class="entre" style="flex-wrap:nowrap;align-items:flex-start">
      <!-- flex:1 + min-width:0 deixam o bloco das descrições encolher: sem isso a
           descrição HC, que é longa, empurrava o contador de pendentes para baixo. -->
      <div style="flex:1;min-width:0">
        <h3 style="margin-bottom:.15rem">{{ item.xProd }}</h3>
        <p class="suave pequeno" style="margin:0">
          Lote <span v-if="item.precisa_lote" class="etiqueta vermelho">não informado na NF<template v-if="item.nLote"> (veio “{{ item.nLote }}”)</template></span><template v-else>{{ item.nLote }}</template> ·
          validade <span v-if="item.precisa_validade" class="etiqueta vermelho">não informada na NF</span><template v-else>{{ f.dataBr(item.dVal) }}
            <span v-if="alertaValidade(item)" :class="['etiqueta', alertaValidade(item)!.cor]">{{ alertaValidade(item)!.texto }}</span></template> ·
          valor unitário {{ f.moeda(item.vUnCom) }}
          <template v-if="Number(item.lote_e_serie)"><br><span class="etiqueta azul"
            title="O mesmo produto veio na nota com vários lotes, cada um com 1 unidade: é o número de série.">o lote da NF é o número de série — será gravado também como série</span></template>
        </p>
        <!-- A descrição do hospital aparece AQUI, logo abaixo da do fornecedor: as
             duas lado a lado são a conferência — se não descreverem o mesmo
             material, o código AGHU digitado está errado. -->
        <DescritivoHc :codigo="aghu" />
      </div>
      <div style="text-align:right;flex:0 0 auto">
        <div class="numero">{{ item.qtd_pendente }}</div>
        <div class="rotulo">pendentes de {{ item.qtd_total }}</div>
      </div>
    </div>

    <form v-if="item.qtd_pendente > 0" method="post" :action="`/almoxarifado/nf/${nota.chave_nf}/receber`" style="margin-top:1rem">
      <input type="hidden" name="id_item" :value="item.id_item">

      <!-- Campos opcionais primeiro, obrigatórios por último: o código de barras
           costuma ser bipado, e o leitor manda Enter sozinho depois do código. -->
      <div class="grade grade-3">
        <div class="campo">
          <label>Fornecedor</label>
          <input type="text" name="fornecedor" :defaultValue="nota.fornecedor">
        </div>
        <div class="campo">
          <label>Classificação</label>
          <select name="tipo_entrada" v-model="tipo">
            <option v-for="(nome, codigo) in tipos" :key="codigo" :value="codigo">{{ nome }}</option>
          </select>
          <template v-if="tipo === 'consignado'">
            <label style="margin-top:.5rem">Código consignado</label>
            <CampoCodigoConsignado :aghu="aghu" />
          </template>
        </div>
        <div class="campo">
          <label>Números de série <span class="opcional">(um por linha, opcional)</span></label>
          <textarea name="numeros_serie" rows="1" :placeholder="Number(item.lote_e_serie) ? `em branco = ${item.nLote}` : ''"></textarea>
        </div>
      </div>

      <div class="grade grade-3" style="margin-top:.75rem">
        <div class="campo">
          <label class="obrigatorio">Código AGHU</label>
          <input type="text" name="codigo_aghu" required autocomplete="off" v-model="aghu"
                 :list="`aghus-${item.id_item}`" class="campo-codigo-aghu">
          <datalist v-if="item.aghus_conhecidos?.length" :id="`aghus-${item.id_item}`">
            <option v-for="a in item.aghus_conhecidos" :key="a" :value="a"></option>
          </datalist>
        </div>
        <div class="campo">
          <label class="obrigatorio">Marca / Fabricante</label>
          <input type="text" name="marca_fabricante" required autocomplete="off" :list="`marcas-${item.id_item}`">
          <datalist v-if="item.marcas_conhecidas?.length" :id="`marcas-${item.id_item}`">
            <option v-for="m in item.marcas_conhecidas" :key="m" :value="m"></option>
          </datalist>
          <div v-if="item.marcas_conhecidas?.length > 1" class="aviso alerta" style="margin-top:.5rem;padding:.5rem .75rem;font-size:.85rem">
            Este código já veio de mais de uma marca antes
            ({{ item.marcas_conhecidas.join(', ') }}) — confira qual é a desta entrega,
            não repita a última sem olhar a embalagem.
          </div>
          <div v-else-if="item.marcas_conhecidas?.length" class="dica">
            Já visto antes como <strong>{{ item.marcas_conhecidas[0] }}</strong> — confirme
            que é a mesma marca desta entrega antes de aceitar a sugestão.
          </div>
        </div>
        <div class="campo">
          <label class="obrigatorio">Quantidade a receber</label>
          <input type="number" name="quantidade" min="1" :max="item.qtd_pendente" :defaultValue="item.qtd_pendente" required>
          <div class="dica">Pode receber parcialmente — o restante continua pendente.</div>
        </div>
      </div>

      <div v-if="item.precisa_lote || item.precisa_validade" class="aviso alerta" style="margin-top:.75rem">
        <strong>A NF não trouxe {{ item.precisa_lote ? 'o lote' : '' }}{{ item.precisa_lote && item.precisa_validade ? ' e ' : '' }}{{ item.precisa_validade ? 'a validade' : '' }}.</strong>
        Digite conforme a embalagem. Se bipar a etiqueta completa da embalagem no código de barras, o lote e a
        validade dela são usados quando estes campos ficarem em branco.
        <div class="grade grade-3" style="margin-top:.6rem">
          <div v-if="item.precisa_lote" class="campo">
            <label class="obrigatorio">Lote</label>
            <input type="text" name="nLote_manual" autocomplete="off" placeholder="como está na embalagem">
          </div>
          <div v-if="item.precisa_validade" class="campo">
            <label class="obrigatorio">Validade</label>
            <input type="date" name="dVal_manual" required>
          </div>
        </div>
        <div class="dica">Se entrar mais de um lote, dê entrada em partes: informe a quantidade de cada lote por vez.</div>
      </div>

      <div v-if="item.codigo_sugerido" class="campo" style="margin-top:.75rem">
        <label>Código de barras <span class="etiqueta verde">veio da NF</span></label>
        <input type="text" :defaultValue="item.codigo_sugerido" readonly tabindex="-1"
               style="background:var(--fundo, #f3f5f8);cursor:not-allowed" aria-readonly="true">
        <div class="dica">Preenchido pelo cEAN da nota — não precisa bipar. Na embalagem, este número
          aparece junto com validade e lote, ex.: (01){{ item.codigo_sugerido }}(17)…(10)…; o sistema separa sozinho na hora do uso.</div>
      </div>
      <div v-else class="campo" style="margin-top:.75rem">
        <label class="obrigatorio">Código de barras</label>
        <div class="dica" style="margin-bottom:.3rem">A NF não trouxe o código de barras deste item. Bipe a embalagem
          (pode ser a etiqueta completa) ou marque “Sem código de barras”.</div>
        <input type="text" name="codigo_barras" v-model="codigoBarras" :required="!semCodigo" :disabled="semCodigo"
               :placeholder="semCodigo ? 'gerado automaticamente' : 'bipe a embalagem'" class="campo-codigo-barras">
        <label class="pequeno" style="display:flex;gap:.4rem;align-items:center;font-weight:400;margin-top:.5rem">
          <input type="checkbox" name="sem_codigo_barras" value="1" style="width:auto" class="marca-sem-codigo" v-model="semCodigo">
          <strong>Sem código de barras</strong> — gerar QR
        </label>
        <div v-if="semCodigo" class="dica marca-dica-qr">
          Será gerado <span class="mono">AGHU(lote {{ item.nLote || '—' }})</span> e a etiqueta abre para imprimir.
        </div>
      </div>

      <button class="botao" style="margin-top:.75rem">Registrar entrada</button>
    </form>
    <p v-else class="aviso sucesso" style="margin:1rem 0 0">Item totalmente recebido.</p>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import CampoCodigoConsignado from './CampoCodigoConsignado.vue';
import DescritivoHc from './DescritivoHc.vue';
import { useFormatos } from '../../utils/formatos';

defineProps<{ item: any; nota: any; tipos: Record<string, string> }>();
const f = useFormatos();
const aghu = ref('');
const codigoBarras = ref('');
const semCodigo = ref(false);
const tipo = ref('aquisicao_propria');

// nov/2026: validade curta em destaque — menos de 30 dias em vermelho, menos de 1 ano em amarelo.
function diasAte(iso: string): number | null {
  if (!iso) return null;
  const alvo = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(alvo.getTime())) return null;
  const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
  return Math.round((alvo.getTime() - hoje.getTime()) / 86400000);
}
function alertaValidade(item: any): { cor: string; texto: string } | null {
  if (item.precisa_validade) return null;
  const d = diasAte(item.dVal);
  if (d === null) return null;
  if (d < 0) return { cor: 'vermelho', texto: `VENCIDO há ${-d} dia(s)` };
  if (d < 30) return { cor: 'vermelho', texto: d === 0 ? 'vence HOJE' : `vence em ${d} dia(s)` };
  if (d < 365) return { cor: 'amarelo', texto: `atenção: vence em ${Math.floor(d / 30)} mês(es)` };
  return null;
}
function estiloValidade(item: any): Record<string, string> {
  const a = alertaValidade(item);
  if (!a) return {};
  return a.cor === 'vermelho'
    ? { borderLeft: '5px solid var(--vermelho, #b3261e)', background: '#fdecea' }
    : { borderLeft: '5px solid #b7791f', background: '#fbf2e2' };
}
watch(semCodigo, (marcado) => { if (marcado) codigoBarras.value = ''; });
</script>
