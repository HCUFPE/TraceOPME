import { defineStore } from 'pinia';
import { ref } from 'vue';
import api from '../services/api';

/** Rótulos e listas do domínio (estados, operações, unidades...), de /api/sistema/meta. */
export const useMetaStore = defineStore('meta', () => {
  const dados = ref<any>(null);
  let carregando: Promise<void> | null = null;

  async function carregar(forcar = false) {
    if (dados.value && !forcar) return;
    if (carregando && !forcar) return carregando;
    carregando = (async () => {
      try {
        const { data } = await api.get('/api/sistema/meta');
        dados.value = data.dados;
      } finally {
        carregando = null;
      }
    })();
    return carregando;
  }

  function limpar() {
    dados.value = null;
  }

  return { dados, carregar, limpar };
});
