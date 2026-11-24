<template>
  <!-- nov/2026: "Reportar problema" — abre um chamado para a Administração. -->
  <button type="button" class="reportar-botao" title="Reportar problema" @click="abrir">
    <ExclamationTriangleIcon class="h-5 w-5" />
    <span class="reportar-texto">Reportar problema</span>
  </button>

  <Teleport to="body">
    <div v-if="aberto" class="opme reportar-fundo" role="dialog" aria-modal="true" @click.self="fechar">
      <div class="reportar-janela">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem">
          <div>
            <h2 style="margin:0">Reportar problema</h2>
            <p class="pequeno suave" style="margin:.2rem 0 0">Vira um chamado para a Administração. A tela em que você está vai junto.</p>
          </div>
          <button type="button" class="botao secundario pequeno" @click="fechar">Fechar</button>
        </div>

        <template v-if="!enviado">
          <div class="campo" style="margin-top:1rem">
            <label class="obrigatorio" for="rp-descricao">O que aconteceu?</label>
            <textarea id="rp-descricao" ref="campo" v-model="descricao" rows="5"
                      placeholder="Ex.: ao bipar o item na sala 03 apareceu a mensagem “…”. Era o paciente do prontuário …"></textarea>
          </div>
          <div class="campo">
            <label>Imagem <span class="opcional">(opcional — print da tela ou foto)</span></label>
            <FotoEtiqueta nome="imagem_chamado" rotulo="Imagem" rotulo-curto="" dica="Confira se dá para ler." @valor="(v: string) => (imagem = v)" />
          </div>
          <p v-if="erro" class="pequeno" style="color:var(--vermelho, #b3261e)">{{ erro }}</p>
          <button type="button" class="botao" :disabled="enviando || descricao.trim().length < 5" @click="enviar">
            {{ enviando ? 'Enviando…' : 'Enviar chamado' }}</button>
        </template>
        <div v-else class="aviso sucesso" style="margin-top:1rem">
          <strong>{{ enviado }}</strong>
          <div style="margin-top:.6rem"><button type="button" class="botao secundario pequeno" @click="novo">Reportar outro problema</button></div>
        </div>

        <div v-if="meus.length" style="margin-top:1.2rem;border-top:1px solid var(--borda);padding-top:.8rem">
          <h3 style="margin:0 0 .4rem;font-size:1rem">Seus chamados</h3>
          <div v-for="c in meus" :key="c.id_chamado" class="pequeno" style="padding:.35rem 0;border-bottom:1px solid var(--borda)">
            <strong>nº {{ c.id_chamado }}</strong> · {{ f.dataHoraBr(c.criado_em) }} ·
            <span :class="['etiqueta', c.status === 'resolvido' ? 'verde' : c.status === 'andamento' ? 'azul' : 'amarelo']">{{ situacoes[c.status] || c.status }}</span>
            <div class="suave" style="white-space:pre-wrap">{{ resumo(c.descricao) }}</div>
            <div v-if="c.resposta" style="white-space:pre-wrap"><strong>Resposta:</strong> {{ c.resposta }}</div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ExclamationTriangleIcon } from '@heroicons/vue/24/outline';
import FotoEtiqueta from './FotoEtiqueta.vue';
import { getJson, postJson } from '../../services/opme';
import { useFormatos } from '../../utils/formatos';
import { APP_VERSION } from '../../config/version';

const f = useFormatos();
const route = useRoute();
const aberto = ref(false);
const descricao = ref('');
const imagem = ref('');
const enviando = ref(false);
const enviado = ref('');
const erro = ref('');
const meus = ref<any[]>([]);
const situacoes = ref<Record<string, string>>({});
const campo = ref<HTMLTextAreaElement | null>(null);

function resumo(t: string) { return t.length > 160 ? t.slice(0, 160) + '…' : t; }

async function carregarMeus() {
  try {
    const r: any = await getJson('/api/chamados/meus');
    meus.value = r.chamados || [];
    situacoes.value = r.situacoes || {};
  } catch { /* lista é só informativa */ }
}

async function abrir() {
  aberto.value = true;
  erro.value = '';
  carregarMeus();
  await nextTick();
  campo.value?.focus();
}
function fechar() { aberto.value = false; }
function novo() { enviado.value = ''; descricao.value = ''; imagem.value = ''; nextTick(() => campo.value?.focus()); }

async function enviar() {
  erro.value = '';
  enviando.value = true;
  try {
    const r: any = await postJson('/api/chamados/abrir', {
      descricao: descricao.value, imagem: imagem.value, pagina: route.fullPath, versao: APP_VERSION.value,
    });
    if (r.ok) {
      enviado.value = r.mensagem;
      descricao.value = '';
      imagem.value = '';
      carregarMeus();
    } else {
      erro.value = r.mensagem || 'Não foi possível enviar.';
    }
  } catch {
    erro.value = 'Falha de conexão. Tente de novo.';
  } finally {
    enviando.value = false;
  }
}
</script>

<style scoped>
.reportar-botao {
  display: inline-flex; align-items: center; gap: .4rem; padding: .45rem .8rem; margin-right: .6rem;
  border: 1px solid #f0dcb8; border-radius: 999px; background: #fbf2e2; color: #8a5a00;
  font-size: .9rem; font-weight: 600; cursor: pointer;
}
.reportar-botao:hover { background: #f6e6c6; }
@media (max-width: 720px) { .reportar-texto { display: none; } }
.reportar-fundo {
  position: fixed; inset: 0; z-index: 60; background: rgba(15, 23, 42, .45);
  display: flex; align-items: flex-start; justify-content: center; padding: 5vh 1rem; overflow: auto;
}
.reportar-janela {
  background: #fff; border-radius: 12px; padding: 1.25rem 1.4rem; width: 100%; max-width: 640px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, .25); border-top: 5px solid #b7791f;
}
</style>
