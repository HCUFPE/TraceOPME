<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Salas</h1>
        <p>Quando o paciente entrar, clique em <strong>Abrir sala</strong> no nome dele. Em seguida, dê ciência do material que a
           farmácia mandou, registre o uso e, ao terminar a bipagem, finalize a sala.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/sala-procedimento">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" />

    <p v-if="!d.unidade_atual" class="aviso alerta">Escolha a unidade (Bloco Cirúrgico ou Hemodinâmica) para ver as salas.</p>

    <div class="grade-salas">
      <div v-for="s in d.salas" :key="s.chave" :class="['sala', 'c-' + s.cor]">
        <div class="sala-topo">
          <div class="sala-num"><small>SALA</small>{{ s.sala }}</div>
          <div class="sala-sit">{{ s.situacao }}</div>
        </div>

        <!-- Sala aberta: o paciente que está nela e o próximo passo -->
        <template v-if="emAndamento(s)">
          <div class="corpo">
            <div class="paciente"><strong>{{ s.atual.paciente || 'Paciente' }}</strong> <span class="mono">· {{ s.atual.prontuario }}</span></div>
            <div class="pequeno suave">{{ s.atual.especialidade }} · aberta às {{ s.atual.horas.aberta }}
              <template v-if="!s.atual.sala_aberta_registrada"> (sozinha)</template></div>
            <ol class="passos">
              <li v-for="(e, i) in d.etapas" :key="e.chave" :class="passo(s.atual, i)" :title="e.rotulo">
                <span class="bola">{{ passo(s.atual, i) === 'feito' ? '✓' : i + 1 }}</span>
                <span class="rot">{{ e.rotulo }}</span>
              </li>
            </ol>
            <div class="botoes">
              <a v-if="s.atual.dispensa_pendente" class="botao" :href="`/dispensacoes/atendimento/${s.atual.id_atendimento}`">
                Dar ciência do material recebido</a>
              <a :class="['botao', { secundario: s.atual.dispensa_pendente }]" :href="`/bipagem/registrar_uso?atendimento=${s.atual.id_atendimento}`">Registrar uso</a>
              <a class="botao secundario" :href="`/sala-procedimento/atendimento/${s.atual.id_atendimento}/concluir`">Finalizar registro de uso e devoluções</a>
              <a class="link" :href="`/sala-procedimento/atendimento/${s.atual.id_atendimento}`">ficha</a>
            </div>
            <ul v-if="s.atual.alertas.length" class="avisos">
              <li v-for="(a, i) in s.atual.alertas" :key="i">{{ a.tipo === 'pedido' ? '📋' : '⚠' }} {{ a.texto }}</li>
            </ul>
          </div>
        </template>

        <!-- Sala sem paciente: quem está agendado para ela hoje -->
        <div v-else class="corpo">
          <p v-if="!agendados(s).length" class="pequeno suave" style="margin:0">Nenhum paciente agendado para abrir nesta sala hoje.
            <a href="/sala-procedimento/atendimentos">Incluir paciente</a></p>
          <form v-for="pr in agendados(s)" :key="pr.id_atendimento" method="post" class="abrir"
                :action="`/sala-procedimento/atendimento/${pr.id_atendimento}/abrir-sala`">
            <input type="hidden" name="voltar" value="/sala-procedimento/salas">
            <div style="flex:1;min-width:0">
              <strong>{{ pr.paciente || 'Paciente' }}</strong> <span class="mono pequeno">· {{ pr.prontuario }}</span><br>
              <span class="pequeno suave">{{ pr.especialidade }}<template v-if="pr.hora_agendada"> · {{ pr.hora_agendada }}</template>
                <template v-if="pr.dispensa_pendente"> · material da farmácia chegando</template></span>
            </div>
            <button class="botao">▶ Abrir sala</button>
          </form>
        </div>

        <div v-if="s.na_farmacia.length" class="na-farmacia">
          <div v-for="pr in s.na_farmacia" :key="pr.id_atendimento" class="pequeno">
            Anterior: <strong>{{ pr.paciente || pr.prontuario }}</strong> — sala finalizada às {{ pr.farmacia_desde }}, farmácia conferindo.</div>
        </div>

        <!-- Chamados -->
        <div class="chamados">
          <span v-for="c in s.chamados" :key="c.id_chamado" :class="['chip-ch', 'ch-' + c.status]">
            {{ c.icone }} {{ c.tipo_rotulo }}: {{ c.status === 'aberto' ? `chamado há ${c.espera_min} min` : `${c.responsavel} a caminho` }}</span>
          <details class="chamar">
            <summary>Chamar maqueiro / limpeza</summary>
            <form v-for="(t, chave) in d.tipos_chamado" :key="chave" method="post" action="/sala-procedimento/salas/chamado" class="form-ch">
              <input type="hidden" name="sala" :value="s.sala">
              <input type="hidden" name="tipo" :value="chave">
              <span class="ic">{{ t.icone }}</span>
              <select name="motivo" :aria-label="'Motivo: ' + t.rotulo">
                <option v-for="m in t.motivos" :key="m" :value="m">{{ m }}</option>
              </select>
              <button class="botao pequeno" :disabled="s.chamados.some((c: any) => c.tipo === chave)">Chamar {{ t.rotulo.toLowerCase() }}</button>
            </form>
          </details>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';

const props = defineProps<{ d: any }>();
const NA_SALA = ['aberta', 'ciencia', 'em_uso'];
const emAndamento = (s: any) => s.atual && NA_SALA.includes(s.atual.etapa);
const agendados = (s: any) => (s.procedimentos || []).filter((p: any) => p.etapa === 'agendado');
function passo(pr: any, i: number): string {
  const etapas = props.d.etapas || [];
  if (pr.horas[etapas[i].chave]) return 'feito';
  const ultima = etapas.reduce((m: number, e: any, j: number) => (pr.horas[e.chave] ? j : m), -1);
  return i === ultima + 1 ? 'agora' : '';
}
</script>

<style scoped>
.grade-salas { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 1rem; }
.sala { background: #fff; border: 1px solid var(--borda, #d9dee5); border-radius: 14px; overflow: hidden; display: flex; flex-direction: column; }
.c-cinza { --c: #8a94a3; } .c-azul-claro { --c: #7fb2e5; } .c-azul { --c: #1f6fc4; } .c-ciano { --c: #0f9fb0; }
.c-verde { --c: #1e9e5a; } .c-roxo { --c: #7a4fc4; } .c-lilas { --c: #b9a3e3; } .c-verde-escuro { --c: #2f6b45; }
.sala-topo { background: var(--c); color: #fff; display: flex; justify-content: space-between; align-items: center; padding: .55rem .9rem; }
.c-cinza .sala-topo, .c-azul-claro .sala-topo, .c-lilas .sala-topo { color: #10233a; }
.sala-num { font-size: 1.9rem; font-weight: 800; line-height: 1; display: flex; flex-direction: column; }
.sala-num small { font-size: .62rem; letter-spacing: .12em; }
.sala-sit { font-weight: 700; text-align: right; }
.corpo { padding: .7rem .9rem; display: flex; flex-direction: column; gap: .5rem; }
.paciente { font-size: 1.05rem; }
.passos { list-style: none; padding: 0; margin: .2rem 0; display: grid; grid-template-columns: repeat(6, 1fr); position: relative; }
.passos::before { content: ''; position: absolute; top: .7rem; left: 8%; right: 8%; height: 3px; background: #e3e7ed; }
.passos li { display: flex; flex-direction: column; align-items: center; text-align: center; gap: .15rem; position: relative; z-index: 1; }
.bola { width: 1.45rem; height: 1.45rem; border-radius: 50%; display: grid; place-items: center; font-size: .72rem; font-weight: 700;
  background: #fff; border: 2px solid #cfd6df; color: #8a94a3; }
.passos li.feito .bola { background: #1e9e5a; border-color: #1e9e5a; color: #fff; }
.passos li.agora .bola { border-color: #1f6fc4; color: #1f6fc4; box-shadow: 0 0 0 4px rgba(31,111,196,.2); }
.rot { font-size: .62rem; line-height: 1.1; }
.botoes { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
.link { font-size: .9rem; }
.avisos { list-style: none; padding: .45rem .6rem; margin: 0; border-radius: 8px; background: #fff6dc; color: #6b4b00; font-size: .84rem; font-weight: 600; }
.abrir { display: flex; align-items: center; gap: .6rem; border: 1px solid #e3e7ed; border-radius: 10px; padding: .55rem .7rem; margin: 0; }
.na-farmacia { margin: 0 .9rem .5rem; background: #f4effc; border-radius: 8px; padding: .4rem .6rem; }
.chamados { margin-top: auto; border-top: 1px solid #eef1f5; padding: .5rem .9rem .7rem; display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
.chip-ch { font-size: .8rem; font-weight: 600; padding: .2rem .55rem; border-radius: 999px; background: #fff4e5; border: 1px solid #f0c37a; }
.chip-ch.ch-direcionado { background: #eaf3ff; border-color: #a9c8f0; }
.chamar { width: 100%; }
.chamar summary { cursor: pointer; font-size: .9rem; font-weight: 600; color: var(--azul, #0c3a67); }
.form-ch { display: flex; gap: .4rem; align-items: center; margin: .45rem 0 0; }
.form-ch select { flex: 1; min-width: 0; }
.form-ch .ic { font-size: 1.3rem; }
</style>
