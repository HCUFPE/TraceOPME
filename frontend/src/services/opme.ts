/**
 * Cliente das telas do TraceOPME sobre a API do framework.
 *
 * Toda tela do TraceOPME tem a mesma URL da v17 (ex.: /almoxarifado/nf/123) e
 * os dados vêm de /api + a mesma URL. A resposta é um envelope:
 *   { tela, dados }          → dados da tela (a view é escolhida por `tela`)
 *   { redirecionar }         → seguir para outra tela
 *   { aviso }                → mensagem (faixa verde/vermelha ou janela)
 *   { sessao }               → unidade/farmácia escolhida (fica no navegador)
 * Arquivos (PDF, CSV, PNG) e as respostas JSON da bipagem vêm sem envelope.
 */
import api from './api';
import router from '../router';
import { useAvisoStore } from '../stores/aviso';
import { useSessaoStore } from '../stores/sessao';

export interface Envelope {
  tela?: string;
  dados?: any;
  redirecionar?: string;
  aviso?: { texto: string; tipo: string; acoes?: [string, string][] };
  sessao?: Record<string, string>;
  status?: number;
}

/** URL da API para um caminho de tela. */
export function urlApi(caminho: string): string {
  if (caminho.startsWith('/api/')) return caminho;
  return '/api' + (caminho.startsWith('/') ? caminho : '/' + caminho);
}

/** Aplica aviso e sessão do envelope (chamado em toda resposta). */
export function aplicarEnvelope(env: Envelope, manterAvisoNaProximaTela = true) {
  if (!env || typeof env !== 'object') return;
  if (env.sessao) useSessaoStore().atualizar(env.sessao);
  if (env.aviso) useAvisoStore().mostrar(env.aviso as any, manterAvisoNaProximaTela);
}

/** Mensagem legível de um erro do axios ({"detail": "..."} do framework). */
export function mensagemDeErro(e: any): string {
  const d = e?.response?.data;
  if (d?.detail) return typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail);
  if (d?.mensagem) return d.mensagem;
  return e?.message || 'Falha de conexão. Verifique a rede e tente de novo.';
}

/** Carrega os dados de uma tela. */
export async function carregarTela(caminho: string): Promise<Envelope> {
  const { data } = await api.get(urlApi(caminho));
  return data as Envelope;
}

/** Converte um objeto simples em FormData (listas viram campos repetidos). */
export function paraFormData(dados: Record<string, any>): FormData {
  const fd = new FormData();
  Object.entries(dados || {}).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    if (Array.isArray(v)) v.forEach((x) => fd.append(k, String(x)));
    else if (v instanceof Blob) fd.append(k, v);
    else fd.append(k, String(v));
  });
  return fd;
}

/** Envia uma ação de tela (formulário). Devolve o envelope já aplicado. */
export async function enviarAcao(caminho: string, dados: FormData | Record<string, any>): Promise<Envelope> {
  const corpo = dados instanceof FormData ? dados : paraFormData(dados);
  const { data } = await api.post(urlApi(caminho), corpo, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data as Envelope;
}

/** Chamada JSON (bipagem, identificação, buscas ao vivo). */
export async function postJson<T = any>(caminho: string, corpo: any): Promise<T> {
  const { data } = await api.post(urlApi(caminho), corpo);
  return data as T;
}

export async function getJson<T = any>(caminho: string, params?: Record<string, any>): Promise<T> {
  const { data } = await api.get(urlApi(caminho), { params });
  return data as T;
}

/** Segue o redirecionamento do envelope. Devolve true se mudou de tela. */
export async function seguir(env: Envelope, recarregar?: () => void): Promise<boolean> {
  if (!env.redirecionar) return false;
  const destino = env.redirecionar;
  if (/^https?:\/\//.test(destino)) {
    const u = new URL(destino);
    await irPara(u.pathname + u.search + u.hash, recarregar);
    return true;
  }
  await irPara(destino, recarregar);
  return true;
}

async function irPara(destino: string, recarregar?: () => void) {
  const atual = router.currentRoute.value;
  const semHash = destino.split('#')[0];
  if (semHash === atual.fullPath.split('#')[0] || decodeURI(semHash) === decodeURI(atual.fullPath.split('#')[0])) {
    // Mesma tela: só recarrega os dados (e rola até a âncora, se houver, ou ao
    // topo — como o recarregamento da página na v17, onde aparece o aviso).
    if (recarregar) recarregar();
    if (destino.includes('#')) {
      await router.replace(destino).catch(() => undefined);
      rolarAte(destino);
    } else {
      rolarTopo();
    }
    return;
  }
  await router.push(destino).catch(() => undefined);
}

/** Rola a área de conteúdo do layout (e a janela) até o topo. */
export function rolarTopo() {
  const area = document.getElementById('conteudo-rolagem');
  if (area) area.scrollTo({ top: 0, behavior: 'smooth' });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

export function rolarAte(destino: string) {
  const ancora = destino.split('#')[1];
  if (!ancora) return;
  setTimeout(() => {
    const el = document.getElementById(ancora);
    if (el) {
      if (el.tagName === 'DETAILS') { (el as HTMLDetailsElement).open = true; el.hidden = false; }
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, 120);
}

/** Baixa um arquivo autenticado (PDF, CSV, TXT) e entrega ao navegador. */
export async function baixarArquivo(caminho: string, abrirNaAba = false) {
  const resposta = await api.get(urlApi(caminho), { responseType: 'blob' });
  const tipo = resposta.headers['content-type'] || 'application/octet-stream';
  const blob = new Blob([resposta.data], { type: tipo });
  // Uma resposta JSON aqui é envelope (ex.: redirecionar com aviso), não arquivo.
  if (tipo.includes('application/json')) {
    const env = JSON.parse(await blob.text());
    aplicarEnvelope(env, true);
    await seguir(env);
    return;
  }
  const url = URL.createObjectURL(blob);
  const disp = resposta.headers['content-disposition'] || '';
  const m = disp.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const nome = m ? decodeURIComponent(m[1]) : (caminho.split('?')[0].split('/').pop() || 'arquivo');
  if (abrirNaAba || disp.startsWith('inline')) {
    window.open(url, '_blank');
  } else {
    const a = document.createElement('a');
    a.href = url;
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Endereço local (blob) de uma imagem autenticada, ex.: QR Code da etiqueta. */
export async function urlImagem(caminho: string): Promise<string> {
  const resposta = await api.get(urlApi(caminho), { responseType: 'blob' });
  return URL.createObjectURL(resposta.data);
}
