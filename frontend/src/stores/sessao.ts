import { defineStore } from 'pinia';
import { ref } from 'vue';

/**
 * "Sessão de trabalho" do TraceOPME: em qual farmácia / unidade a pessoa está
 * trabalhando agora (Bloco Cirúrgico ou Hemodinâmica). Na v17 isso ficava na
 * sessão do servidor; aqui fica no navegador (por usuário) e vai em cada
 * chamada no cabeçalho X-Sessao. O backend devolve as mudanças no envelope.
 */
const CHAVE = 'traceopme-sessao';

function ler(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(CHAVE) || '{}') || {};
  } catch {
    return {};
  }
}

export const useSessaoStore = defineStore('sessao', () => {
  const valores = ref<Record<string, string>>(ler());

  function atualizar(novos: Record<string, string> | null | undefined) {
    if (!novos) return;
    valores.value = { ...valores.value, ...novos };
    try { localStorage.setItem(CHAVE, JSON.stringify(valores.value)); } catch { /* sem armazenamento */ }
  }

  function limpar() {
    valores.value = {};
    try { localStorage.removeItem(CHAVE); } catch { /* ignora */ }
  }

  /** Valor do cabeçalho X-Sessao (base64 de JSON, seguro para cabeçalho HTTP). */
  function cabecalho(): string {
    const json = JSON.stringify(valores.value || {});
    return btoa(unescape(encodeURIComponent(json)));
  }

  return { valores, atualizar, limpar, cabecalho };
});
