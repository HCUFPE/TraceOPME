/**
 * Utilidades comuns das views do TraceOPME: formatos/rótulos, usuário logado,
 * sessão de trabalho e envio de ações (com o mesmo tratamento de envelope que
 * os formulários comuns recebem na PaginaOpme).
 */
import { inject } from 'vue';
import { useFormatos } from '../utils/formatos';
import { useAuthStore } from '../stores/auth';
import { useSessaoStore } from '../stores/sessao';
import { useMetaStore } from '../stores/meta';
import { useAvisoStore } from '../stores/aviso';
import {
  baixarArquivo, enviarAcao, getJson, mensagemDeErro, postJson, urlImagem, type Envelope,
} from '../services/opme';

interface PaginaOpme {
  recarregar: () => Promise<void>;
  tratarResposta: (env: Envelope) => Promise<void>;
}

export function useTela() {
  const f = useFormatos();
  const auth = useAuthStore();
  const sessao = useSessaoStore();
  const meta = useMetaStore();
  const avisos = useAvisoStore();
  const pagina = inject<PaginaOpme>('opmePagina', {
    recarregar: async () => undefined,
    tratarResposta: async () => undefined,
  });

  /** Envia uma ação de tela (como um formulário POST) e trata a resposta. */
  async function acao(caminho: string, dados: FormData | Record<string, any> = {}) {
    try {
      const env = await enviarAcao(caminho, dados);
      await pagina.tratarResposta(env);
      return env;
    } catch (e) {
      avisos.mostrar({ texto: mensagemDeErro(e), tipo: 'erro' }, false);
      return null;
    }
  }

  async function baixar(caminho: string, abrirNaAba = false) {
    try {
      await baixarArquivo(caminho, abrirNaAba);
    } catch (e) {
      avisos.mostrar({ texto: mensagemDeErro(e), tipo: 'erro' }, false);
    }
  }

  return { f, auth, sessao, meta, avisos, pagina, acao, baixar, postJson, getJson, urlImagem, mensagemDeErro };
}
