<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Corrigir peça registrada no uso</h1>
        <p>Quando o bipe pegou outra unidade do mesmo material — por exemplo uma parada em outro
          estoque — e a peça que a farmácia dispensou ficou na sala sem uso.</p>
      </div>
      <a v-if="at.id_atendimento" class="botao secundario"
         :href="`/sala-procedimento/atendimento/${at.id_atendimento}`">Voltar ao prontuário</a>
    </div>

    <form v-if="!at.id_atendimento" class="cartao" method="get" action="/sala-procedimento/correcao-uso">
      <label>Procedimento (código do atendimento)
        <input name="atendimento" placeholder="AT-..." required></label>
      <button class="botao">Abrir</button>
      <p class="pequeno suave" style="margin:.6rem 0 0">Você também chega aqui pelo botão
        “Corrigir peça do uso”, na ficha do prontuário.</p>
    </form>

    <template v-else>
      <div class="cartao">
        <h2 style="margin:0">Prontuário {{ at.prontuario }}</h2>
        <p class="pequeno suave" style="margin:.2rem 0 0">{{ d.descricao }}</p>
      </div>

      <p v-if="!d.pendencias.length" class="cartao vazio">
        Nenhum uso deste procedimento parece ter pegado a peça errada. Esta tela só mostra uso
        registrado <strong>sem dispensação</strong> quando existe, no mesmo paciente, peça do mesmo
        material que a farmácia dispensou e continua na sala.
      </p>

      <div v-for="p in d.pendencias" :key="p.id_unidade" class="cartao">
        <h2 style="margin:0 0 .2rem">{{ p.material }} <span class="pequeno suave">AGHU {{ p.codigo_aghu }}</span></h2>
        <p class="pequeno suave" style="margin:0 0 .7rem">
          Bipado como usado em {{ f.dataHoraBr(p.usado_em) }} por {{ p.usado_por }} — sem dispensação.
        </p>

        <div class="par">
          <div class="lado errado">
            <div class="rotulo">Está registrada como usada</div>
            <strong>lote {{ p.nLote || '—' }}</strong>
            <div class="pequeno">val. {{ f.dataBr(p.dVal) || '—' }}</div>
            <div class="pequeno suave">{{ p.farmacia || 'sem farmácia' }}</div>
            <div class="pequeno">volta para: <strong>{{ p.volta_para }}</strong></div>
          </div>
          <div class="seta">→</div>
          <div class="lado certo">
            <div class="rotulo">Passa a ser a usada</div>
            <form method="post" :action="`/sala-procedimento/correcao-uso/${p.id_unidade}`">
              <label v-for="t in p.trocas" :key="t.id_unidade" class="opcao">
                <input type="radio" name="id_na_sala" :value="t.id_unidade"
                       :checked="p.trocas.length === 1">
                <span><strong>lote {{ t.nLote || '—' }}</strong>
                  <span class="pequeno"> · val. {{ f.dataBr(t.dVal) || '—' }} · {{ t.material }}</span>
                  <br><span class="pequeno suave">dispensada pela farmácia, está na sala</span>
                  <br v-if="t.aghu_diferente"><span v-if="t.aghu_diferente" class="etiqueta amarelo pequeno">
                    cadastro com AGHU diferente ({{ t.codigo_aghu }}) — confira o cadastro depois</span></span>
              </label>
              <label>Motivo da correção (fica na auditoria)
                <input name="motivo" required minlength="10"
                       placeholder="ex.: o bipe pegou peça de outro estoque; a usada foi a dispensada"></label>
              <button class="botao">Corrigir o registro</button>
            </form>
          </div>
        </div>
      </div>

      <p class="pequeno suave">Nada é apagado: o uso anterior continua no histórico das duas peças,
        marcado como corrigido, com quem corrigiu e por quê.</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const at = computed(() => props.d.atendimento || {});
</script>

<style scoped>
.par { display: flex; gap: 1rem; align-items: stretch; flex-wrap: wrap; }
.lado { flex: 1 1 18rem; border: 1px solid rgba(0,0,0,.15); border-radius: .5rem; padding: .7rem; }
.lado.errado { border-left: 4px solid var(--vermelho, #c0392b); }
.lado.certo { border-left: 4px solid var(--verde, #1e7a4b); }
.rotulo { font-size: .8rem; text-transform: uppercase; letter-spacing: .03em; opacity: .7; margin-bottom: .3rem; }
.seta { align-self: center; font-size: 1.6rem; opacity: .5; }
.opcao { display: flex; gap: .5rem; align-items: flex-start; margin: .3rem 0; }
</style>
