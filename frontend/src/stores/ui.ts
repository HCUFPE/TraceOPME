import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useUiStore = defineStore('ui', () => {
  const isLoading = ref(false);
  // Título da tela atual (mostrado no cabeçalho do layout e na aba do navegador).
  const titulo = ref('');

  function setLoading(loading: boolean) {
    isLoading.value = loading;
  }

  function setTitulo(t: string) {
    titulo.value = t || '';
    document.title = t ? `${t} · TraceOPME` : 'TraceOPME | HC-UFPE';
  }

  return { isLoading, setLoading, titulo, setTitulo };
});
