<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Contando {{ inv.local_rotulo }}</h1>
        <p class="mono">{{ inv.id_inventario }}</p>
        <p v-if="inv.observacao">{{ inv.observacao }}</p>
      </div>
      <div class="acoes">
        <a class="botao secundario" href="/inventario">Voltar</a>
      </div>
    </div>

    <div id="tela-inventario" class="bipagem" :data-inventario="inv.id_inventario">
      <div>
        <div class="caixa-scanner">
          <label for="codigo-inv">Bipe o código de barras</label>
          <input type="text" id="codigo-inv" ref="campo" v-model="codigo" autocomplete="off" autocapitalize="off"
                 spellcheck="false" placeholder="aguardando leitura…" inputmode="text"
                 @keydown.enter.prevent="contar(codigo.trim())">
          <!-- v18.11.1: caixa fechada — várias unidades iguais num bip só -->
          <div style="display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin-top:.5rem">
            <label for="qtd-inv" class="pequeno" style="margin:0">Unidades por bip</label>
            <input type="number" id="qtd-inv" v-model.number="qtd" min="1" max="500" data-sem-foco="1" style="width:6rem"
                   :style="qtd > 1 ? 'font-weight:700;border:2px solid var(--azul, #0c3a67);background:#eef4fb' : ''" @change="focar()">
            <span v-if="qtd > 1" id="aviso-qtd-inv" class="pequeno" style="color:var(--azul, #0c3a67);font-weight:600">
              o próximo bip conta {{ qtd }} unidades (caixa fechada) — depois volta para 1</span>
          </div>

          <div class="contador-grande" style="margin-top:1rem">
            <div><div class="numero" id="inv-conferidos">{{ progresso.conferidos }}</div>
                 <div class="rotulo">conferidos</div></div>
            <div><div class="numero" id="inv-faltam">{{ progresso.faltam }}</div>
                 <div class="rotulo">ainda não bipados</div></div>
            <div><div class="numero" id="inv-pendencias">{{ progresso.pendencias }}</div>
                 <div class="rotulo">pendências</div></div>
          </div>
          <p class="pequeno suave" style="margin:.4rem 0 0">
            O sistema espera <strong id="inv-esperados">{{ progresso.esperados }}</strong>
            material(is) neste local. “Ainda não bipados” só vira falta de verdade
            quando você encerrar a contagem.
          </p>

          <ResultadoLeitura ref="resultado">
            <div v-if="!lido" class="resultado-linha" style="background:var(--cinza-claro)">
              <div class="icone">⌖</div>
              <div><div class="titulo">Pronto para contar</div>
                   <div class="detalhe">O resultado de cada leitura aparece aqui.</div></div>
            </div>
          </ResultadoLeitura>

          <div class="linha-botoes">
            <button type="button" class="botao secundario" id="inv-confirmar" data-sem-foco="1" @click="contar(codigo.trim())">
              Confirmar código digitado
            </button>
            <label class="pequeno" style="display:flex;align-items:center;gap:.4rem;font-weight:400">
              <input type="checkbox" id="som" v-model="somLigado" data-sem-foco="1" style="width:auto">
              som de confirmação
            </label>
          </div>
        </div>

        <div class="cartao" style="margin-top:1rem">
          <h2>Leituras desta contagem</h2>
          <ul class="lista-bipados" id="inv-lista">
            <li v-for="(l, n) in leituras" :key="n">
              <div class="produto">
                <strong>{{ l.produto }}</strong>
                <span>{{ l.detalhe }}</span>
              </div>
              <span :class="['etiqueta', l.situacao === 'confere' ? 'verde' : 'amarelo']">{{ l.rotulo }}</span>
            </li>
          </ul>
          <p v-if="!leituras.length" class="vazio">Nenhuma leitura ainda.</p>
        </div>
      </div>

      <aside>
        <div class="cartao" style="border-left:5px solid var(--verde)">
          <h2>Encerrar e ver o relatório</h2>
          <p class="suave pequeno">
            Encerre só quando tiver bipado tudo que existe fisicamente aqui. No
            relatório aparece o que faltou, o que estava em outro lugar e o que
            apareceu a mais.
          </p>
          <p class="suave pequeno">
            A contagem <strong>não move material</strong>: ela aponta as pendências e
            você corrige depois, pelas telas normais, com o motivo registrado.
          </p>
          <form method="post" :action="`/inventario/${inv.id_inventario}/encerrar`"
                :data-confirmar="`Encerrar a contagem ${inv.id_inventario}? Depois disso ela não aceita mais leituras.`">
            <button class="botao" data-sem-foco="1">Encerrar contagem</button>
          </form>
          <p class="pequeno suave" style="margin-top:.6rem">
            Pode sair desta tela e voltar depois — a contagem fica aberta e as
            leituras já feitas continuam registradas.
          </p>
        </div>

        <div class="cartao" style="margin-top:1rem">
          <h2>O que cada situação quer dizer</h2>
          <div v-for="(nome, chave) in d.situacoes" :key="chave" style="padding:.4rem 0;border-bottom:1px solid var(--borda)">
            <span :class="['etiqueta', String(chave) === 'confere' ? 'verde' : 'amarelo']">{{ nome }}</span>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import ResultadoLeitura from '../../components/opme/ResultadoLeitura.vue';
import { useLeitor } from '../../composables/useLeitor';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f, postJson } = useTela();

const inv = computed(() => props.d.inv);
const progresso = reactive({ ...(props.d.progresso || {}) });
const codigo = ref('');
const campo = ref<HTMLInputElement | null>(null);
const resultado = ref<InstanceType<typeof ResultadoLeitura> | null>(null);
const somLigado = ref(true);
const lido = ref(false);
const { bip, vibrar, focar } = useLeitor(campo, { somLigado });

interface Linha { produto: string; detalhe: string; situacao: string; rotulo: string }
const leituras = ref<Linha[]>((props.d.leituras || []).map((l: any) => ({
  produto: l.xProd || l.codigo_lido,
  detalhe: `${l.codigo_aghu ? `AGHU ${l.codigo_aghu} · ` : ''}lote ${l.nLote || '—'} · val. ${f.dataBr(l.dVal) || '—'}`,
  situacao: l.situacao,
  rotulo: l.situacao_rotulo,
})));

const ROTULOS: Record<string, string> = {
  confere: 'Confere',
  local_divergente: 'Está em outro lugar no sistema',
  nao_deveria_existir: 'O sistema já deu baixa neste material',
  excedente: 'Apareceu mais unidade do que o sistema tem',
  desconhecido: 'Não está cadastrado',
};

const qtd = ref(1);
let ocupado = false;
let ultimoInstante = 0;

async function contar(c: string) {
  if (!c || ocupado) return;
  // Sem a trava de repetição da tela de fluxo: na contagem, bipar o mesmo
  // código de novo é o gesto normal. Só barramos a leitura dupla acidental
  // do próprio leitor, muito mais rápida que a mão humana.
  const agora = Date.now();
  if (agora - ultimoInstante < 250) return;
  ultimoInstante = agora;
  ocupado = true;
  codigo.value = '';
  lido.value = true;
  try {
    const dados: any = await postJson('/inventario/api/bipar', { id_inventario: inv.value.id_inventario, codigo: c, quantidade: Math.max(1, Math.floor(Number(qtd.value) || 1)) });
    qtd.value = 1;
    if (!dados.ok) {
      resultado.value?.mostrar(false, 'Não foi possível contar', dados.mensagem);
      bip(200, 0.3);
    } else {
      const confere = dados.situacao === 'confere';
      const rotulo = ROTULOS[dados.situacao] || dados.situacao;
      resultado.value?.mostrar(confere ? true : 'alerta', dados.item?.produto || 'Material sem cadastro', `${rotulo} — ${dados.mensagem}`);
      leituras.value.unshift({
        produto: (dados.quantidade > 1 ? `${dados.quantidade}× ` : '') + (dados.item?.produto || 'Material sem cadastro'),
        detalhe: `AGHU ${dados.item?.aghu ?? ''} · lote ${dados.item?.lote ?? ''} · val. ${dados.item?.validade ?? ''}`,
        situacao: dados.situacao,
        rotulo,
      });
      bip(confere ? 880 : 620, confere ? 0.12 : 0.22);
      vibrar(confere ? 40 : [50, 40, 50]);
    }
    if (dados.progresso) Object.assign(progresso, dados.progresso);
  } catch {
    resultado.value?.mostrar(false, 'Falha de conexão', 'Verifique a rede e leia o código novamente.');
    bip(200, 0.3);
  } finally {
    ocupado = false;
    focar();
  }
}
</script>
