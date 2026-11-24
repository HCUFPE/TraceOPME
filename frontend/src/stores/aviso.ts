import { defineStore } from 'pinia';
import { ref } from 'vue';

export interface Aviso {
  texto: string;
  tipo: 'sucesso' | 'erro' | 'alerta' | 'info' | 'janela' | string;
  acoes?: [string, string][];
}

/** Mensagem da última ação (equivale ao "flash" da v17): faixa colorida ou janela vermelha. */
export const useAvisoStore = defineStore('aviso', () => {
  const atual = ref<Aviso | null>(null);
  // Mantém o aviso durante a navegação que a própria ação disparou.
  let proteger = false;

  function mostrar(aviso: Aviso | null | undefined, manterNaProximaTela = true) {
    if (!aviso) return;
    atual.value = aviso;
    proteger = manterNaProximaTela;
  }

  /** Chamado a cada troca de tela: o aviso some, exceto o recém-criado. */
  function aoNavegar() {
    if (proteger) {
      proteger = false;
      return;
    }
    atual.value = null;
  }

  function fechar() {
    atual.value = null;
  }

  return { atual, mostrar, aoNavegar, fechar };
});
