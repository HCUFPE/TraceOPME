<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Material por classificação</h1>
        <p>Consignado, aquisição própria, doação e empréstimo em um período —
           base para a conferência com o fornecedor e para a prestação de contas.</p>
      </div>
      <div class="acoes">
        <a v-if="d.linhas.length" class="botao secundario" data-baixar :href="urlCsv">
          Exportar CSV{{ d.detalhado ? ' detalhado' : '' }}
        </a>
        <a class="botao secundario" href="/consultas"> Voltar</a>
      </div>
    </div>

    <form method="get" action="/consultas/classificacao" class="cartao">
      <div class="filtros">
        <div class="campo"><label>De</label><input type="date" name="inicio" :defaultValue="d.inicio"></div>
        <div class="campo"><label>Até</label><input type="date" name="fim" :defaultValue="d.fim"></div>
        <div class="campo">
          <label>Classificação</label>
          <select name="tipo_entrada">
            <option value="">todas</option>
            <option v-for="(nome, codigo) in d.tipos" :key="codigo" :value="codigo" :selected="d.tipo_entrada === codigo">{{ nome }}</option>
          </select>
        </div>
        <div class="campo"><label>Fornecedor</label>
          <input type="text" name="fornecedor" :defaultValue="d.fornecedor"></div>
        <div class="campo">
          <label>Contar pela data de</label>
          <select name="base">
            <option value="entrada" :selected="d.base !== 'uso'">entrada no almoxarifado</option>
            <option value="uso" :selected="d.base === 'uso'">uso no paciente</option>
          </select>
        </div>
        <div class="campo">
          <label>Mostrar</label>
          <select name="detalhado">
            <option value="1" :selected="!!d.detalhado">cada material, com paciente, lote e validade</option>
            <option value="0" :selected="!d.detalhado">resumo por produto (totais)</option>
          </select>
        </div>
        <button class="botao">Filtrar</button>
      </div>
      <p class="suave pequeno" style="margin:.6rem 0 0">
        “Entrada no almoxarifado” responde <em>o que entrou</em> no período;
        “uso no paciente” responde <em>o que foi consumido</em>.
        Para pedir a nota do consignado ao fornecedor, conte pela data de <em>uso no
        paciente</em> — é o consumo que gera o faturamento, e o fornecedor emite a
        nota contra lote, série e paciente.
      </p>
    </form>

    <div v-if="d.totais?.length" class="grade grade-4" style="margin-bottom:1.5rem">
      <div v-for="(t, n) in d.totais" :key="n" class="cartao">
        <div class="rotulo">{{ nomeTipo(t.tipo_entrada) }}</div>
        <div class="numero">{{ t.quantidade }}</div>
        <div class="rotulo">{{ f.moeda(t.valor_total) }}</div>
      </div>
    </div>

    <div class="cartao">
      <h2>{{ d.linhas.length }} {{ d.detalhado ? 'material(is)' : 'linha(s)' }} de {{ f.dataBr(d.inicio) }} a {{ f.dataBr(d.fim) }}</h2>

      <div v-if="d.cortada" class="aviso alerta">
        <strong>Lista cortada em {{ d.limite_detalhe }} materiais.</strong> Há mais
        material no período do que cabe nesta consulta — não mande esta relação ao
        fornecedor como se fosse completa. Reduza o período, ou filtre por um
        fornecedor de cada vez, e exporte em partes.
      </div>

      <p v-if="d.detalhado && !d.somente_utilizados" class="suave pequeno" style="margin:0 0 .8rem">
        Contando pela data de entrada: material que ainda não foi usado aparece
        sem paciente, porque ainda não há procedimento vinculado.
      </p>

      <div v-if="d.linhas.length && d.detalhado" class="tabela-rolagem">
        <table class="tabela-detalhe">
          <thead>
            <tr><th>Paciente</th><th>Procedimento</th><th>Código</th><th>Produto</th>
                <th>Lote</th><th>Validade</th><th>Nº de série</th><th>Fornecedor</th>
                <th>Cód. consignado</th><th class="num">Valor</th><th>NF</th></tr>
          </thead>
          <tbody>
            <tr v-for="(l, n) in d.linhas" :key="n">
              <td>{{ l.paciente || '—' }}
                <div v-if="l.prontuario" class="pequeno suave">prontuário {{ l.prontuario }}</div></td>
              <td class="pequeno">{{ f.dataBr(l.data_procedimento) || '—' }}</td>
              <td class="mono">{{ l.codigo_aghu || '—' }}
                <div v-if="l.codigo_barras" class="pequeno suave">{{ l.codigo_barras }}</div></td>
              <td>{{ l.xProd }}
                <div v-if="l.marca_fabricante" class="pequeno suave">{{ l.marca_fabricante }}</div></td>
              <td class="mono">{{ l.nLote || '—' }}</td>
              <td class="mono">{{ f.dataBr(l.dVal) || '—' }}</td>
              <td class="mono pequeno">{{ l.numero_serie || '—' }}</td>
              <td class="pequeno">{{ l.fornecedor || '—' }}</td>
              <td class="mono pequeno">{{ l.codigo_consignado || '—' }}</td>
              <td class="num">{{ f.moeda(l.vUnCom) }}</td>
              <td class="pequeno"><template v-if="l.numero_nf">{{ l.numero_nf }}</template><span v-else class="etiqueta amarelo">a pedir</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="d.linhas.length" class="tabela-rolagem">
        <table>
          <thead>
            <tr><th>Classificação</th><th>Código AGHU</th><th>Produto</th><th>Fornecedor</th>
                <th class="num">Qtd.</th><th class="num">Valor</th><th>Entradas</th></tr>
          </thead>
          <tbody>
            <tr v-for="(l, n) in d.linhas" :key="n">
              <td><span :class="['etiqueta', l.tipo_entrada === 'consignado' ? 'roxo' : 'azul']">{{ nomeTipo(l.tipo_entrada) }}</span></td>
              <td class="mono">{{ l.codigo_aghu || '—' }}</td>
              <td>{{ l.xProd }}</td>
              <td class="pequeno">{{ l.fornecedor || '—' }}</td>
              <td class="num">{{ l.quantidade }}</td>
              <td class="num">{{ f.moeda(l.valor_total) }}</td>
              <td class="pequeno suave">{{ f.dataBr(l.primeira_entrada) }}<template v-if="l.ultima_entrada !== l.primeira_entrada"> a {{ f.dataBr(l.ultima_entrada) }}</template></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum material encontrado com esses filtros no período.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const nomeTipo = (t: string) => props.d.tipos?.[t] ?? t;
const urlCsv = computed(() => {
  const p = new URLSearchParams({
    inicio: props.d.inicio || '', fim: props.d.fim || '', tipo_entrada: props.d.tipo_entrada || '',
    fornecedor: props.d.fornecedor || '', base: props.d.base || '', detalhado: props.d.detalhado ? '1' : '0', exportar: '1',
  });
  return `/consultas/classificacao?${p.toString()}`;
});
</script>
