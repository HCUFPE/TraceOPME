<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Consulta por prontuário</h1>
        <p>Materiais implantados no paciente, com lote, validade e nota fiscal de origem.</p>
      </div>
      <div class="acoes">
        <button v-if="d.linhas?.length" type="button" class="botao secundario" @click="imprimir">Imprimir</button>
        <a class="botao secundario" href="/consultas"> Voltar</a>
      </div>
    </div>

    <form method="get" action="/consultas/prontuario" class="cartao" ref="formBusca">
      <div class="filtros">
        <div class="campo" style="flex:1">
          <label>Número do prontuário</label>
          <input type="text" name="numero" :defaultValue="d.numero" inputmode="numeric" autofocus
                 @input="digitado = ($event.target as HTMLInputElement).value">
        </div>
        <!-- Trocar o prontuário volta ao procedimento mais recente do novo paciente —
             por isso a data só vai no formulário quando o prontuário já é este. -->
        <div v-if="d.numero && d.datas?.length" class="campo" style="flex:1">
          <label>Procedimento</label>
          <select name="data" id="data-procedimento" :disabled="digitado.trim() !== d.numero" @change="formBusca?.requestSubmit()">
            <option v-for="x in d.datas" :key="x.data" :value="x.data" :selected="d.data === x.data">
              {{ f.dataBr(x.data) }} — {{ f.especialidade(x.especialidade) }} · {{ x.quantidade }} un
            </option>
            <option value="todas" :selected="d.data === 'todas'">Todas as datas (histórico completo)</option>
          </select>
        </div>
        <button class="botao">Consultar</button>
      </div>
    </form>

    <!-- v18: sem prontuário — quem teve material registrado no dia/período -->
    <template v-if="!d.numero">
      <form method="get" action="/consultas/prontuario" class="cartao">
        <h2 style="margin-top:0">Prontuários com material registrado no período</h2>
        <div class="filtros">
          <div class="campo"><label>De</label><input type="date" name="inicio" :defaultValue="d.inicio"></div>
          <div class="campo"><label>Até</label><input type="date" name="fim" :defaultValue="d.fim"></div>
          <button class="botao secundario">Filtrar</button>
        </div>
      </form>
      <div class="cartao">
        <h2>{{ d.periodo?.length || 0 }} procedimento(s)
          <span class="pequeno suave">{{ f.dataBr(d.inicio) }}<template v-if="d.fim && d.fim !== d.inicio"> a {{ f.dataBr(d.fim) }}</template></span></h2>
        <div v-if="d.periodo?.length" class="tabela-rolagem">
          <table>
            <thead><tr><th>Data</th><th>Prontuário</th><th>Paciente</th><th>Local</th><th>Especialidade</th><th class="num">Implantes</th><th></th></tr></thead>
            <tbody>
              <tr v-for="p in d.periodo" :key="p.id_atendimento">
                <td>{{ f.dataBr(p.data) }}<span v-if="p.hora_inicio" class="pequeno suave"> {{ p.hora_inicio }}</span></td>
                <td class="mono"><strong>{{ p.prontuario }}</strong></td>
                <td>{{ p.paciente || '—' }}</td>
                <td>{{ f.rotuloUnidade(p.unidade) }}<template v-if="p.sala"> — sala {{ p.sala }}</template></td>
                <td>{{ f.especialidade(p.especialidade) }}</td>
                <td class="num">{{ p.usados }}</td>
                <td><a class="botao pequeno secundario" :href="`/consultas/prontuario?numero=${encodeURIComponent(p.prontuario)}&data=${p.data}`">Abrir ficha</a></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhum material registrado neste período.</p>
      </div>
    </template>

    <div v-if="d.numero && d.linhas?.length" class="cartao" style="border-left:5px solid var(--azul)">
      <div class="entre">
        <h2>Descritivo cirúrgico</h2>
        <div class="linha-botoes" style="margin:0">
          <button type="button" class="botao pequeno" id="copiar-descritivo" data-sem-foco="1" @click="copiar">📋 Copiar</button>
          <a class="botao secundario pequeno" data-baixar :href="url('txt')">Baixar TXT</a>
          <a class="botao secundario pequeno" data-baixar data-abrir :href="url('pdf')">Abrir PDF</a>
        </div>
      </div>
      <p class="suave pequeno">
        Copie e cole no descritivo cirúrgico do prontuário eletrônico. Traz código AGHU,
        quantidade, lote, validade e fornecedor de cada material implantado.
      </p>
      <textarea id="texto-descritivo" ref="area" :rows="Math.min((d.descritivo || '').split('\n').length + 1, 18)"
                readonly class="mono pequeno" :value="d.descritivo"
                style="width:100%;white-space:pre;overflow-x:auto"></textarea>
      <span v-if="copiado" id="aviso-copia" class="pequeno" style="color:var(--verde)">Copiado para a área de transferência.</span>
    </div>

    <template v-if="d.numero">
      <div class="cartao">
        <h2>{{ d.linhas.length }} material(is) implantado(s) — prontuário {{ d.numero }}
            <span class="suave pequeno">· {{ periodo }}</span></h2>
        <div v-if="d.linhas.length" class="tabela-rolagem">
          <table>
            <thead>
              <tr><th>Data</th><th>Sala</th><th>Especialidade</th><th>Produto</th>
                  <th>Lote</th><th>Validade</th><th>Nº série</th><th>Fornecedor</th><th>NF</th><th>Registrado por</th></tr>
            </thead>
            <tbody>
              <tr v-for="l in d.linhas" :key="l.id_unidade">
                <td>{{ f.dataBr(l.data_procedimento) }}</td>
                <td>{{ l.sala }}</td>
                <td>{{ f.especialidade(l.especialidade) }}</td>
                <td><a :href="`/consultas/item/${l.id_unidade}`">{{ l.xProd }}</a><br>
                    <span class="suave pequeno">{{ l.marca_fabricante || '' }}</span></td>
                <td class="mono">{{ l.nLote || '—' }}</td>
                <td>{{ f.dataBr(l.dVal) || '—' }}</td>
                <td class="mono pequeno">{{ l.numero_serie || '—' }}</td>
                <td class="pequeno">{{ l.fornecedor || '—' }}</td>
                <td class="pequeno">{{ l.numero_nf || '—' }}</td>
                <td class="pequeno">{{ l.usuario_uso || '—' }}<br>
                    <span class="suave">{{ f.dataHoraBr(l.data_uso) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhum material registrado como utilizado para este prontuário.</p>
      </div>

      <div class="cartao">
        <h2>{{ d.devolucoes.length }} material(is) devolvido(s) sem uso à farmácia
            <span class="suave pequeno">· {{ periodo }}</span></h2>
        <div v-if="d.devolucoes.length" class="tabela-rolagem">
          <table>
            <thead>
              <tr><th>Data</th><th>Sala</th><th>Especialidade</th><th>Produto</th><th>AGHU</th>
                  <th>Lote</th><th>Validade</th><th>Devolvido em</th><th>Devolvido por (sala)</th><th>Recebido por (farmácia)</th></tr>
            </thead>
            <tbody>
              <tr v-for="(x, n) in d.devolucoes" :key="n">
                <td>{{ f.dataBr(x.data_procedimento) }}</td>
                <td>{{ x.sala }}</td>
                <td>{{ f.especialidade(x.especialidade) }}</td>
                <td><a :href="`/consultas/item/${x.id_unidade}`">{{ x.descritivo_hospital || x.xProd }}</a><br>
                    <span class="suave pequeno">{{ x.fornecedor || '' }}</span></td>
                <td class="mono pequeno">{{ x.codigo_aghu || '—' }}</td>
                <td class="mono">{{ x.nLote || '—' }}</td>
                <td>{{ f.dataBr(x.dVal) || '—' }}</td>
                <td class="pequeno">{{ f.dataHoraBr(x.data_evento) }}</td>
                <td class="pequeno"><span class="etiqueta azul">{{ x.devolvido_por || x.bipado_por || '—' }}</span><template v-if="x.bipado_por && x.devolvido_por && x.devolvido_por !== x.bipado_por"><br><span class="suave">login {{ x.bipado_por }}</span></template></td>
                <td class="pequeno"><span v-if="x.recebido_por" class="etiqueta verde">{{ x.recebido_por }}</span><template v-else>—</template></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhuma devolução registrada para este prontuário.</p>
        <p class="suave pequeno" style="margin:.6rem 0 0">
          Usos e devoluções juntos, em ordem de horário, e em planilha:
          <a :href="`/consultas/eventos?prontuario=${encodeURIComponent(d.numero)}&tipo=uso_devolucao${d.data === 'todas' ? '' : '&inicio=' + d.data}`">histórico de movimentações deste prontuário</a>.
        </p>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const digitado = ref<string>(props.d.numero || '');
const formBusca = ref<HTMLFormElement | null>(null);
const area = ref<HTMLTextAreaElement | null>(null);
const copiado = ref(false);
const periodo = computed(() => (props.d.data === 'todas' ? 'histórico completo' : `procedimento de ${f.dataBr(props.d.data)}`));

function url(formato: string) {
  return `/consultas/prontuario?numero=${encodeURIComponent(props.d.numero)}&data=${encodeURIComponent(props.d.data || '')}&formato=${formato}`;
}
function imprimir() { window.print(); }

async function copiar() {
  const el = area.value;
  if (!el) return;
  try {
    // navigator.clipboard só existe em HTTPS ou localhost; em rede interna
    // por HTTP o navegador bloqueia, então há o caminho antigo como reserva.
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(el.value);
    } else {
      el.removeAttribute('readonly');
      el.select();
      document.execCommand('copy');
      el.setAttribute('readonly', 'readonly');
      window.getSelection()?.removeAllRanges();
    }
    copiado.value = true;
    setTimeout(() => { copiado.value = false; }, 2500);
  } catch {
    el.select();
    window.alert('Não foi possível copiar automaticamente. O texto já está selecionado: use Ctrl+C.');
  }
}
</script>
