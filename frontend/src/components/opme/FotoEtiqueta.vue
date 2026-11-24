<template>
  <!-- nov/2026: foto da etiqueta pela câmera do computador — sempre opcional. -->
  <div class="foto-etiqueta">
    <input type="hidden" :name="nome" :value="foto">

    <div v-if="foto" style="display:flex;gap:1rem;align-items:flex-start;flex-wrap:wrap">
      <img :src="foto" :alt="rotulo" style="max-width:260px;max-height:200px;border:1px solid var(--borda);border-radius:6px">
      <div>
        <p class="pequeno" style="margin:0 0 .5rem"><strong>{{ rotulo }} anexada.</strong> {{ dica }}</p>
        <button type="button" class="botao secundario pequeno" @click="abrir">Tirar outra</button>
        <button type="button" class="botao secundario pequeno" style="margin-left:.4rem" @click="remover">Remover</button>
      </div>
    </div>

    <div v-else-if="ligada" style="display:grid;gap:.5rem;max-width:520px">
      <video ref="video" autoplay playsinline muted style="width:100%;border-radius:6px;background:#000"></video>
      <div style="display:flex;gap:.5rem">
        <button type="button" class="botao" @click="capturar">Capturar foto</button>
        <button type="button" class="botao secundario" @click="desligar">Cancelar</button>
      </div>
    </div>

    <div v-else style="display:flex;gap:.6rem;align-items:center;flex-wrap:wrap">
      <button v-if="temCamera" type="button" class="botao secundario" @click="abrir">📷 Tirar foto{{ rotuloCurto }}</button>
      <label class="botao secundario" style="cursor:pointer;margin:0">
        {{ temCamera ? 'ou escolher imagem' : `📷 ${rotulo} (escolher imagem)` }}
        <input type="file" accept="image/*" capture="environment" style="display:none" @change="escolherArquivo">
      </label>
      <span class="pequeno suave">Opcional.</span>
    </div>
    <p v-if="erro" class="pequeno" style="color:var(--vermelho, #b3261e);margin:.4rem 0 0">{{ erro }}</p>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref } from 'vue';

withDefaults(defineProps<{ nome?: string; rotulo?: string; rotuloCurto?: string; dica?: string }>(), {
  nome: 'foto_etiqueta', rotulo: 'Foto da etiqueta', rotuloCurto: ' da etiqueta',
  dica: 'Confira se lote e validade estão legíveis.',
});
const emit = defineEmits<{ (e: 'mudou', temFoto: boolean): void; (e: 'valor', dataUrl: string): void }>();

const foto = ref('');
const ligada = ref(false);
const erro = ref('');
const video = ref<HTMLVideoElement | null>(null);
let fluxo: MediaStream | null = null;
// A câmera só abre em conexão segura (https ou o próprio computador, 127.0.0.1/localhost).
const temCamera = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && window.isSecureContext;

const LADO_MAX = 1400;

function definir(dataUrl: string) {
  foto.value = dataUrl;
  emit('mudou', !!dataUrl);
  emit('valor', dataUrl);
}

async function abrir() {
  erro.value = '';
  try {
    fluxo = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1920 } }, audio: false });
    ligada.value = true;
    await nextTick();
    if (video.value) video.value.srcObject = fluxo;
  } catch {
    erro.value = 'Não consegui abrir a câmera (sem câmera ou permissão negada). Você pode escolher uma imagem.';
    desligar();
  }
}

function desligar() {
  fluxo?.getTracks().forEach((t) => t.stop());
  fluxo = null;
  ligada.value = false;
}

function reduzir(origem: CanvasImageSource, largura: number, altura: number): string {
  const escala = Math.min(1, LADO_MAX / Math.max(largura, altura));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(largura * escala);
  canvas.height = Math.round(altura * escala);
  canvas.getContext('2d')!.drawImage(origem, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.82);
}

function capturar() {
  const v = video.value;
  if (!v || !v.videoWidth) { erro.value = 'A câmera ainda está abrindo. Tente de novo.'; return; }
  definir(reduzir(v, v.videoWidth, v.videoHeight));
  desligar();
}

function escolherArquivo(ev: Event) {
  erro.value = '';
  const arquivo = (ev.target as HTMLInputElement).files?.[0];
  (ev.target as HTMLInputElement).value = '';
  if (!arquivo) return;
  if (!arquivo.type.startsWith('image/')) { erro.value = 'Escolha um arquivo de imagem.'; return; }
  const img = new Image();
  const url = URL.createObjectURL(arquivo);
  img.onload = () => { definir(reduzir(img, img.naturalWidth, img.naturalHeight)); URL.revokeObjectURL(url); };
  img.onerror = () => { erro.value = 'Não consegui abrir a imagem.'; URL.revokeObjectURL(url); };
  img.src = url;
}

function remover() { definir(''); }
defineExpose({ remover });

onBeforeUnmount(desligar);
</script>
