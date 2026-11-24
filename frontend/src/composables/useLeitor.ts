/**
 * Leitura contínua de código de barras (telas de bipagem).
 *
 * O leitor funciona como teclado e envia Enter ao final da leitura. A tela é
 * construída em volta disso: o campo nunca perde o foco, nenhum clique é
 * necessário e cada leitura devolve resposta em menos de 1 s. Portado do
 * app.js da v17.
 */
import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue';

let contextoAudio: AudioContext | null = null;

export function useLeitor(campo: Ref<HTMLInputElement | null>, opcoes: { somLigado?: Ref<boolean> } = {}) {
  const somLigado = opcoes.somLigado ?? ref(true);
  let bloqueado = false; // ex.: janela vermelha aberta

  function bip(frequencia: number, duracao = 0.12) {
    if (!somLigado.value) return;
    try {
      const Ctx = (window.AudioContext || (window as any).webkitAudioContext);
      contextoAudio = contextoAudio || new Ctx();
      const oscilador = contextoAudio.createOscillator();
      const ganho = contextoAudio.createGain();
      oscilador.connect(ganho);
      ganho.connect(contextoAudio.destination);
      oscilador.frequency.value = frequencia;
      oscilador.type = 'sine';
      ganho.gain.setValueAtTime(0.12, contextoAudio.currentTime);
      ganho.gain.exponentialRampToValueAtTime(0.001, contextoAudio.currentTime + duracao);
      oscilador.start();
      oscilador.stop(contextoAudio.currentTime + duracao);
    } catch { /* som é acessório */ }
  }

  function vibrar(padrao: number | number[]) {
    if (navigator.vibrate) { try { navigator.vibrate(padrao); } catch { /* ignora */ } }
  }

  function focar() {
    const el = campo.value;
    if (!el || el.disabled || bloqueado) return;
    const ativo = document.activeElement as HTMLElement | null;
    if (ativo && ativo !== el && ativo.dataset && ativo.dataset.semFoco === '1') return;
    // preventScroll: devolver o foco não pode rolar a página.
    el.focus({ preventScroll: true });
  }

  function bloquear(sim: boolean) {
    bloqueado = sim;
  }

  function aoPerderFoco() {
    setTimeout(() => {
      const ativo = document.activeElement as HTMLElement | null;
      // Clicou num link, botão ou outro campo: deixa o clique acontecer.
      if (ativo && ativo !== document.body && ativo.closest && ativo.closest('a, button, input, select, textarea, summary')) return;
      focar();
    }, 60);
  }

  function aoClicarNaTela(evento: MouseEvent) {
    const alvo = evento.target as HTMLElement;
    if (alvo.closest('input, select, textarea, button, a, label, summary')) return;
    focar();
  }

  onMounted(() => {
    campo.value?.addEventListener('blur', aoPerderFoco);
    document.addEventListener('click', aoClicarNaTela);
    window.addEventListener('focus', focar);
    setTimeout(focar, 50);
  });
  onBeforeUnmount(() => {
    campo.value?.removeEventListener('blur', aoPerderFoco);
    document.removeEventListener('click', aoClicarNaTela);
    window.removeEventListener('focus', focar);
  });

  return { bip, vibrar, focar, bloquear, somLigado };
}
