<template>
  <!-- v17 — confirmação grande de cada leitura: VERDE quando registrou (fecha
       sozinho em poucos segundos, ou na próxima leitura), VERMELHO quando não
       registrou — fica até a pessoa CLICAR em OK. Enter não fecha, senão a
       próxima leitura do leitor fecharia o aviso sem ninguém ler. -->
  <!-- v18.10: falha mostra o MOTIVO em letra grande (com título pelo tipo do problema);
       registrado com alerta fica AMARELO e espera um pouco mais. -->
  <div v-if="aberto" id="confirmacao-bip" :class="['confirmacao-bip', { falha: !ok, 'com-alerta': ok && alertas.length }]"
       role="alertdialog" aria-live="assertive" @click="aoClicar">
    <div class="confirmacao-bip-janela">
      <div class="confirmacao-bip-icone">{{ !ok ? '✕' : alertas.length ? '!' : '✓' }}</div>
      <h2>{{ titulo }}</h2>
      <template v-if="ok">
        <p class="confirmacao-bip-produto">{{ produto }}</p>
        <p class="confirmacao-bip-detalhe">{{ detalhe }}</p>
        <div v-for="(a, i) in alertas" :key="i" class="aviso confirmacao-bip-alerta">⚠ {{ a }}</div>
      </template>
      <template v-else>
        <p v-if="subtitulo" class="confirmacao-bip-sub">{{ subtitulo }}</p>
        <p class="confirmacao-bip-motivo">{{ detalhe }}</p>
        <p class="confirmacao-bip-detalhe">{{ produto }}</p>
        <div v-for="(a, i) in alertas" :key="i" class="aviso">{{ a }}</div>
      </template>
      <button v-if="!ok" type="button" class="botao" id="confirmacao-bip-ok" data-sem-foco="1" @click.stop="fechar">OK, entendi</button>
      <div class="confirmacao-bip-dica">{{ dica }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';

const props = withDefaults(defineProps<{ dicaFalha?: string; tempoOk?: number }>(), {
  dicaFalha: 'Este material NÃO foi registrado. Clique em OK para continuar.',
  tempoOk: 2200,
});
const emit = defineEmits<{ (e: 'fechou', falha: boolean): void }>();

const aberto = ref(false);
const ok = ref(true);
const titulo = ref('');
const subtitulo = ref('');

// Título da falha pelo tipo do problema (o texto completo vem do servidor).
const TIPOS: [RegExp, string][] = [
  [/vencid|validade expirad/i, 'MATERIAL VENCIDO'],
  [/sala ainda não foi aberta|abra a sala/i, 'SALA NÃO ABERTA'],
  [/outro paciente|outro atendimento|outro prontuário/i, 'MATERIAL DE OUTRO PACIENTE'],
  [/lote diferente|outro lote|lote não confere/i, 'LOTE DIFERENTE'],
  [/não encontrad|não cadastrad|desconhecid/i, 'CÓDIGO NÃO ENCONTRADO'],
  [/já (foi )?(utilizad|registrad|bipad)/i, 'JÁ REGISTRADO'],
  [/bloquead|recall/i, 'MATERIAL BLOQUEADO'],
];
const produto = ref('');
const detalhe = ref('');
const dica = ref('');
const alertas = ref<string[]>([]);
let relogio: ReturnType<typeof setTimeout> | null = null;

function mostrar(sucesso: boolean, t: string, p = '', d = '', avisos: string[] = []) {
  if (relogio) { clearTimeout(relogio); relogio = null; }
  ok.value = sucesso;
  titulo.value = t;
  subtitulo.value = '';
  if (!sucesso) {
    const tipo = TIPOS.find(([re]) => re.test(d || ''));
    if (tipo) { titulo.value = tipo[1]; subtitulo.value = t; }
  }
  produto.value = p;
  detalhe.value = d;
  alertas.value = avisos || [];
  aberto.value = true;
  if (sucesso) {
    dica.value = 'Pode bipar o próximo.';
    relogio = setTimeout(fechar, avisos && avisos.length ? 6000 : props.tempoOk);
  } else {
    dica.value = props.dicaFalha;
    (document.activeElement as HTMLElement | null)?.blur?.();
  }
}

function fechar() {
  if (!aberto.value) return;
  if (relogio) { clearTimeout(relogio); relogio = null; }
  const eraFalha = !ok.value;
  aberto.value = false;
  emit('fechou', eraFalha);
}

/** Começou a próxima leitura: o verde sai da frente na hora. */
function fecharSeVerde() {
  if (aberto.value && ok.value) fechar();
}

function aoClicar() {
  if (ok.value) fechar();
}

function bloquearTeclas(evento: KeyboardEvent) {
  // Com o aviso vermelho aberto, nenhuma tecla (nem o Enter do leitor) faz nada.
  if (aberto.value && !ok.value) evento.preventDefault();
}

onMounted(() => document.addEventListener('keydown', bloquearTeclas));
onBeforeUnmount(() => {
  document.removeEventListener('keydown', bloquearTeclas);
  if (relogio) clearTimeout(relogio);
});

defineExpose({ mostrar, fechar, fecharSeVerde, aberto, ok });
</script>

<style>
.confirmacao-bip-motivo { font-size: 1.45rem; font-weight: 700; line-height: 1.3; color: #5c0f0a; margin: .4rem 0 .6rem; }
.confirmacao-bip-sub { font-size: 1rem; font-weight: 700; letter-spacing: .05em; color: var(--vermelho, #b3261e); margin: 0; }
.confirmacao-bip.com-alerta { background: rgba(120, 80, 0, .40); }
.confirmacao-bip.com-alerta .confirmacao-bip-janela { border-color: #d18f00; }
.confirmacao-bip.com-alerta .confirmacao-bip-icone { background: #d18f00; }
.confirmacao-bip.com-alerta h2 { color: #8a5a00; }
.confirmacao-bip-alerta { font-size: 1.1rem; font-weight: 600; background: #fff4d6; border-left: 5px solid #d18f00; }
.confirmacao-bip h2 { font-size: 2rem; }
</style>
