<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Cadastrar empenho</h1>
        <p>Registre o empenho, os dados da licitação e o <strong>código consignado</strong> que ele cobre (com o AGHU
           associado). O saldo é descontado sozinho a cada uso na sala, enquanto o empenho estiver dentro da vigência.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/consignados/empenhos">Voltar</a></div>
    </div>

    <div v-if="r" class="cartao" :style="`border-left:5px solid ${r.erros?.length ? 'var(--vermelho)' : 'var(--verde)'}`">
      <h2>Resultado da importação</h2>
      <p><strong>{{ r.criados }}</strong> empenho(s) cadastrado(s)
        <template v-if="r.repetidos"> · {{ r.repetidos }} já existiam e foram ignorados</template>
        <template v-if="r.erros?.length"> · <strong>{{ r.erros.length }} linha(s) com problema</strong> (não cadastradas)</template></p>
      <template v-if="r.erros?.length">
        <div class="tabela-rolagem"><table>
          <thead><tr><th>Linha</th><th>Problema</th></tr></thead>
          <tbody><tr v-for="(x, n) in r.erros" :key="n"><td class="num">{{ x.linha }}</td><td>{{ x.mensagem }}</td></tr></tbody>
        </table></div>
        <p class="pequeno suave">Corrija essas linhas na planilha e importe de novo — o que já foi cadastrado não duplica.</p>
      </template>
      <a class="botao secundario pequeno" href="/consignados/empenhos">Ver empenhos</a>
    </div>

    <form method="post" action="/consignados/empenhos/importar" enctype="multipart/form-data" class="cartao">
      <h2>Importar de planilha (Excel)</h2>
      <p class="pequeno">Uma linha por empenho. Colunas: <strong>Fornecedor, Código consignado, Código AGHU, Quantidade licitada,
        Valor unitário, Início da vigência, Fim da vigência, Número do processo, Número do pregão, Número de
        registro de licitação</strong>. Opcionais: Número do empenho, Material, Limite de segurança.
        A ordem das colunas não importa — o sistema reconhece pelo título. O Código AGHU pode ficar em branco quando o
        código consignado já está <a href="/consignados/associacoes">associado</a>; preenchido, cria a associação.</p>
      <div style="display:flex;gap:.6rem;align-items:end;flex-wrap:wrap">
        <div class="campo" style="margin:0"><label class="obrigatorio">Planilha (.xlsx ou .csv)</label>
          <input type="file" name="arquivo" accept=".xlsx,.csv" required></div>
        <button class="botao">Importar</button>
        <a class="botao secundario" href="/static/modelo_empenhos.xlsx" download>Baixar modelo</a>
      </div>
    </form>

    <form method="post" action="/consignados/empenhos/novo" class="cartao">
      <h2>Cadastrar um empenho</h2>
      <h3 class="pequeno suave" style="margin:.2rem 0 .6rem">Licitação</h3>
      <div class="grade grade-3">
        <div class="campo"><label>Número do processo</label>
          <input type="text" name="numero_processo" placeholder="Ex.: 23538.001234/2026-11"></div>
        <div class="campo"><label>Número do pregão</label>
          <input type="text" name="numero_pregao" placeholder="Ex.: 45/2026"></div>
        <div class="campo"><label>Número de registro de licitação</label>
          <input type="text" name="numero_registro" placeholder="Ex.: ARP 112/2026"></div>
        <div class="campo"><label>Início da vigência</label>
          <input type="date" name="vigencia_inicio"></div>
        <div class="campo"><label>Fim da vigência</label>
          <input type="date" name="vigencia_fim">
          <div class="dica">Depois do fim da vigência o empenho não recebe mais débito.</div></div>
        <div class="campo"><label>Número do empenho <span class="opcional">(se já houver)</span></label>
          <input type="text" name="numero" placeholder="Ex.: 2026NE000812"></div>
      </div>
      <p class="pequeno suave">Preencha ao menos um dos números (processo, pregão, registro ou empenho).</p>

      <h3 class="pequeno suave" style="margin:1rem 0 .6rem">Material e saldo</h3>
      <div class="grade grade-2">
        <div class="campo"><label class="obrigatorio">Fornecedor</label>
          <input type="text" name="fornecedor" required></div>
        <div class="campo" style="grid-column:1 / -1" id="pares-consignado">
          <label class="obrigatorio">Código(s) consignado(s) coberto(s) e o AGHU de cada um</label>
          <table class="pares-consignado">
            <thead><tr><th>Código consignado</th><th>Código AGHU</th><th>Descrição</th><th></th></tr></thead>
            <tbody>
              <tr v-for="(l, n) in linhas" :key="l.chave">
                <td><input type="text" name="consignado" v-model="l.consignado" :required="n === 0" autocomplete="off"
                           placeholder="ex.: 102739" @change="consultar(l)" @keydown.enter.prevent="consultar(l)"></td>
                <td><input type="text" name="aghu" v-model="l.aghu" autocomplete="off" :readonly="l.associado"
                           :placeholder="l.associado ? '' : 'informe o AGHU'" :class="{ 'so-leitura': l.associado }"></td>
                <td class="pequeno">
                  <span v-if="l.associado" class="etiqueta verde">associado</span>
                  <span v-else-if="l.consultado && l.consignado" class="etiqueta amarelo">novo — a associação será criada</span>
                  {{ l.descricao }}</td>
                <td><button v-if="linhas.length > 1" type="button" class="botao secundario pequeno" @click="linhas.splice(n, 1)">tirar</button></td>
              </tr>
            </tbody>
          </table>
          <button type="button" class="botao secundario pequeno" style="margin-top:.4rem" @click="novaLinha()">+ outro código consignado</button>
          <div class="dica">Todo uso de uma unidade com esse código consignado debita o saldo sozinho. O AGHU vem da
            <a href="/consignados/associacoes">associação código consignado × AGHU</a>; se o código ainda não tem AGHU,
            digite ao lado e a associação é criada junto com o empenho.</div></div>
        <div class="campo"><label>Material <span class="opcional">(opcional — vem do catálogo)</span></label>
          <input type="text" name="material" placeholder="Em branco = descrição HC do primeiro código AGHU"></div>
        <div class="campo"><label>Data do empenho <span class="opcional">(opcional)</span></label>
          <input type="date" name="data_empenho"></div>
        <div class="campo"><label class="obrigatorio">Quantidade licitada (unidades)</label>
          <input type="number" name="quantidade_total" min="1" required></div>
        <div class="campo"><label class="obrigatorio">Valor unitário (R$)</label>
          <input type="text" name="valor_unitario" required placeholder="220,00"></div>
        <div class="campo"><label>Limite de segurança (unidades) <span class="opcional">(opcional)</span></label>
          <input type="number" name="limite_seguranca" min="0" placeholder="Em branco = 20% da quantidade">
          <div class="dica">Quando o saldo chegar a este número, o sistema avisa para providenciar novo empenho.</div></div>
      </div>
      <div class="campo"><label>Observação <span class="opcional">(opcional)</span></label>
        <input type="text" name="observacao"></div>
      <button class="botao">Cadastrar</button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { getJson } = useTela();
const r = computed(() => props.d.resultado_importacao);

type Linha = { chave: number; consignado: string; aghu: string; descricao: string; associado: boolean; consultado: boolean };
let contador = 0;
const linhas = reactive<Linha[]>([]);
function novaLinha() {
  linhas.push({ chave: ++contador, consignado: '', aghu: '', descricao: '', associado: false, consultado: false });
}
novaLinha();

async function consultar(l: Linha) {
  const codigo = l.consignado.trim();
  l.consultado = false;
  if (!codigo) { l.associado = false; l.descricao = ''; return; }
  try {
    const dd: any = await getJson('/consignados/associacoes/consultar', { codigo });
    if (l.consignado.trim() !== codigo) return;
    l.consultado = true;
    l.associado = !!dd.ok;
    if (dd.ok) {
      l.aghu = dd.codigo_aghu;
      l.descricao = dd.descricao || '';
    } else {
      l.descricao = '';
    }
  } catch {
    l.consultado = false;
  }
}
</script>

<style>
table.pares-consignado td { padding: .25rem .4rem .25rem 0; vertical-align: middle; }
table.pares-consignado input.so-leitura { background: var(--fundo-suave, #f3f5f8); }
</style>
