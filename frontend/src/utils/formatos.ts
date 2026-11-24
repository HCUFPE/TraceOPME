/**
 * Formatos e rótulos usados pelas telas do TraceOPME.
 * Equivalem aos filtros/globais dos templates da v17 (data_br, data_hora_br,
 * moeda, rotulo_status, cor_status, rotulo_unidade...). Os rótulos vêm do
 * backend em /api/sistema/meta (store `meta`).
 */
import { useMetaStore } from '../stores/meta';

function texto(valor: unknown): string {
  if (valor === null || valor === undefined) return '';
  return String(valor).trim();
}

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/** Converte vários formatos de data para AAAA-MM-DD ('' se não der). */
export function dataIso(valor: unknown): string {
  let v = texto(valor);
  if (!v) return '';
  v = v.split('T')[0].split(' ')[0];
  let m = v.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return valida(+m[1], +m[2], +m[3]);
  m = v.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) return valida(+m[3], +m[2], +m[1]);
  m = v.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2})$/);
  if (m) return valida(2000 + +m[3] - (+m[3] > 68 ? 100 : 0), +m[2], +m[1]);
  m = v.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
  if (m) return valida(+m[1], +m[2], +m[3]);
  m = v.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (m) return valida(+m[3], +m[2], +m[1]);
  return '';
}

function valida(a: number, m: number, d: number): string {
  const dt = new Date(a, m - 1, d);
  if (dt.getFullYear() !== a || dt.getMonth() !== m - 1 || dt.getDate() !== d) return '';
  return `${a}-${pad(m)}-${pad(d)}`;
}

/** 2026-10-29 → 29/10/2026 (devolve o texto original se não for data). */
export function dataBr(valor: unknown): string {
  const iso = dataIso(valor);
  if (!iso) return texto(valor);
  const [a, m, d] = iso.split('-');
  return `${d}/${m}/${a}`;
}

/** 2026-10-29T14:05:00 → 29/10/2026 14:05 */
export function dataHoraBr(valor: unknown): string {
  const v = texto(valor);
  if (!v) return '';
  const m = v.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?$/);
  if (!m) return v;
  return `${m[3]}/${m[2]}/${m[1]} ${m[4] ?? '00'}:${m[5] ?? '00'}`;
}

/** 1234.5 → R$ 1.234,50 */
export function moeda(valor: unknown): string {
  const n = Number(valor);
  if (valor === null || valor === undefined || valor === '' || Number.isNaN(n)) return 'R$ 0,00';
  return 'R$ ' + n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Número com separador de milhar pt-BR. */
export function numero(valor: unknown, casas = 0): string {
  const n = Number(valor);
  if (Number.isNaN(n)) return texto(valor);
  return n.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

/** Como o filtro |title do Jinja (com '_' trocado por espaço). */
export function titulo(valor: unknown): string {
  return texto(valor).replace(/_/g, ' ').toLowerCase().replace(/(^|[\s\-(])\S/g, (c) => c.toUpperCase());
}

/** Como o filtro |capitalize do Jinja (com '_' trocado por espaço). */
export function capitalizar(valor: unknown): string {
  const t = texto(valor).replace(/_/g, ' ').toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Como '%.1f'|format(v)|replace('.', ',') dos templates da v17. */
export function decimal1(valor: unknown): string {
  const n = Number(valor);
  if (valor === null || valor === undefined || Number.isNaN(n)) return '—';
  return n.toFixed(1).replace('.', ',');
}

export function hojeIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Funções de rótulo dependentes do domínio (precisam do meta carregado). */
export function useFormatos() {
  const meta = useMetaStore();
  return {
    dataBr, dataHoraBr, moeda, numero, dataIso, hojeIso, titulo, capitalizar, decimal1,
    rotuloStatus: (s: string) => meta.dados?.estados?.[s]?.rotulo ?? (s || '—'),
    corStatus: (s: string) => meta.dados?.estados?.[s]?.cor ?? 'cinza',
    localStatus: (s: string) => meta.dados?.estados?.[s]?.local ?? '—',
    rotuloUnidade: (u: string) => meta.dados?.unidades?.[(u || '').trim().toUpperCase()]?.rotulo ?? (u || '—'),
    corUnidade: (u: string) => meta.dados?.unidades?.[(u || '').trim().toUpperCase()]?.cor ?? 'cinza',
    rotuloPapel: (p: string) => meta.dados?.papeis?.[p] ?? 'Desconhecido',
    rotuloModulo: (m: string) => meta.dados?.modulos?.[m] ?? m,
    rotuloFarmacia: (f: string) => meta.dados?.farmacias?.[(f || '').trim().toUpperCase()] ?? 'Farmácia',
    especialidade: (v: unknown) => {
      const s = texto(v);
      return meta.dados?.rotulo_especialidade?.[s.toUpperCase()]
        ?? s.toLowerCase().replace(/(^|\s)\S/g, (c) => c.toUpperCase());
    },
    rotuloEvento: (tipo: string) =>
      meta.dados?.rotulo_tipo_evento?.[tipo]
      ?? (texto(tipo).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())),
    tituloOperacao: (tipo: string) => meta.dados?.operacoes?.[tipo]?.titulo,
    /** Unidades que usam OPME (Bloco Cirúrgico e Hemodinâmica), como o global UNIDADES da v17. */
    unidadesAtivas: (): Record<string, any> => {
      const todas = meta.dados?.unidades || {};
      const ativas: Record<string, any> = {};
      (meta.dados?.unidades_ativas || []).forEach((k: string) => { ativas[k] = todas[k]; });
      return ativas;
    },
    /** nov/2026: todas as unidades da agenda (tela Procedimentos). */
    todasUnidades: (): Record<string, any> => meta.dados?.unidades || {},
    /** Título da operação, ou o rótulo do tipo de evento (como no painel da v17). */
    movimento: (tipo: string) =>
      meta.dados?.operacoes?.[tipo]?.titulo
      ?? meta.dados?.rotulo_tipo_evento?.[tipo]
      ?? (texto(tipo).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())),
  };
}
