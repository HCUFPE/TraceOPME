<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Conciliação por sala e prontuário</h1>
        <p>O que a farmácia dispensou, o que foi usado no paciente e o que voltou — por sala e prontuário
           (cada procedimento é uma linha), pela data do procedimento. “Em aberto” é o que ainda precisa de uso, devolução ou confirmação.</p>
      </div>
      <div class="acoes">
        <a class="botao secundario" data-baixar :href="`/farmacia/conciliacao?inicio=${q(d.inicio)}&fim=${q(d.fim)}&sala=${q(d.sala)}&unidade=${q(d.unidade)}&prontuario=${q(d.prontuario)}&atendimento=${q(d.atendimento)}&formato=csv`">Exportar planilha (CSV)</a>
        <a class="botao secundario" href="/farmacia">Voltar</a>
      </div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" :acao="d.acao_unidade" :pergunta="d.pergunta_unidade" />

    <form method="get" action="/farmacia/conciliacao" class="cartao" style="display:flex;gap:.6rem;align-items:flex-end;flex-wrap:wrap">
      <div class="campo" style="margin:0"><label>De</label><input type="date" name="inicio" :defaultValue="d.inicio"></div>
      <div class="campo" style="margin:0"><label>Até</label><input type="date" name="fim" :defaultValue="d.fim"></div>
      <div class="campo" style="margin:0"><label>Unidade</label>
        <select name="unidade">
          <option value="">todas</option>
          <option v-for="(u, chave) in f.unidadesAtivas()" :key="chave" :value="chave" :selected="chave === d.unidade">{{ u.rotulo }}</option>
        </select></div>
      <div class="campo" style="margin:0"><label>Sala</label><input type="text" name="sala" :defaultValue="d.sala" style="width:5rem"></div>
      <div class="campo" style="margin:0"><label>Prontuário ou paciente</label><input type="text" name="prontuario" :defaultValue="d.prontuario"></div>
      <button class="botao secundario">Filtrar</button>
    </form>

    <div class="grade grade-4" style="margin-bottom:1rem">
      <div class="cartao"><div class="numero">{{ d.total.dispensado }}</div><div class="rotulo">dispensados</div></div>
      <div class="cartao"><div class="numero">{{ d.total.usado }}</div><div class="rotulo">usados (do dispensado)</div></div>
      <div class="cartao"><div class="numero">{{ d.total.devolvido }}</div><div class="rotulo">devolvidos ao estoque</div></div>
      <div class="cartao" :style="d.total.em_aberto ? 'border-left:5px solid var(--amarelo, #d97706)' : ''">
        <div class="numero">{{ d.total.em_aberto }}</div><div class="rotulo">em aberto</div></div>
    </div>

    <div class="cartao">
      <h2>Por sala e prontuário</h2>
      <template v-if="d.salas?.length">
        <div class="tabela-rolagem"><table>
          <thead><tr><th>Local</th><th>Prontuário</th><th class="num">Dispensado</th><th class="num">Usado</th><th class="num">Devolvido</th>
                     <th class="num">Em aberto</th><th class="num">Divergência</th><th class="num">Usado sem dispensação</th><th>Situação</th><th></th></tr></thead>
          <tbody>
            <tr v-for="l in d.salas" :key="l.id_atendimento">
              <td><strong>{{ f.rotuloUnidade(l.unidade) }} — sala {{ l.sala }}</strong></td>
              <td><strong>{{ l.prontuario }}</strong> <span class="suave pequeno">· {{ f.dataBr(l.data_procedimento) }}</span>
                  <template v-if="l.paciente"><br><span class="suave pequeno">{{ l.paciente }}</span></template></td>
              <td class="num">{{ l.dispensado }}</td>
              <td class="num">{{ l.usado }}</td>
              <td class="num">{{ l.devolvido }}</td>
              <td class="num"><span v-if="l.em_aberto" class="etiqueta amarelo">{{ l.em_aberto }}</span><template v-else>0</template></td>
              <td class="num"><span v-if="l.divergencia" class="etiqueta vermelho">{{ l.divergencia }}</span><template v-else>0</template></td>
              <td class="num"><span v-if="l.sem_dispensacao" :class="['etiqueta', l.sem_ciencia ? 'vermelho' : 'cinza']"
                    :title="`${l.sem_ciencia} sem ciência da farmácia`">{{ l.sem_dispensacao }}</span><template v-else>0</template></td>
              <td><span v-if="l.fechado && !l.sem_ciencia" class="etiqueta verde">conciliado</span>
                  <span v-else class="etiqueta amarelo">pendente</span></td>
              <td><a class="pequeno" :href="`/farmacia/conciliacao?inicio=${q(d.inicio)}&fim=${q(d.fim)}&unidade=${q(l.unidade)}&sala=${q(l.sala)}&atendimento=${q(l.id_atendimento)}`">ver itens</a></td>
            </tr>
          </tbody>
        </table></div>
        <p class="pequeno suave">Conciliado = no procedimento, tudo que foi dispensado já foi usado ou devolvido, sem divergência, e a farmácia
          deu ciência dos usos sem dispensação.</p>
      </template>
      <p v-else class="vazio">Nada dispensado nem usado sem dispensação no período.</p>
    </div>

    <div v-if="(d.atendimento || d.sala || d.prontuario) && (d.itens?.length || d.sem_dispensacao?.length)" class="cartao">
      <h2>Itens<template v-if="d.atendimento && d.salas?.length"> — {{ f.rotuloUnidade(d.salas[0].unidade) }} sala {{ d.salas[0].sala }} · prontuário {{ d.salas[0].prontuario }}</template><template v-else-if="d.sala"> — sala {{ d.sala }}</template></h2>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Procedimento</th><th>Material</th><th>Lote</th><th>Caixa</th><th>Dispensado</th><th>Recebido na sala</th><th>Desfecho</th></tr></thead>
        <tbody>
          <tr v-for="(i, n) in d.itens" :key="'i' + n">
            <td class="pequeno"><strong>{{ i.prontuario }}</strong> · {{ f.dataBr(i.data_procedimento) }}<template v-if="i.paciente"><br><span class="suave">{{ i.paciente }}</span></template></td>
            <td>{{ i.descritivo_hospital || i.xProd }} <span class="mono suave pequeno">AGHU {{ i.codigo_aghu || '—' }}</span></td>
            <td class="mono">{{ i.nLote || '—' }}</td>
            <td class="mono pequeno">{{ i.id_caixa || '—' }}</td>
            <td class="pequeno">{{ f.dataHoraBr(i.bipado_em) }}<br><span class="suave">{{ i.bipado_por }}</span></td>
            <td class="pequeno">{{ i.recebido_por || '—' }}</td>
            <td><span :class="['etiqueta', ({ usado: 'azul', devolvido: 'verde', divergencia: 'vermelho' } as Record<string, string>)[i.desfecho] || 'amarelo']">{{ i.rotulo_desfecho }}</span></td>
          </tr>
          <tr v-for="(s, n) in d.sem_dispensacao" :key="'s' + n">
            <td class="pequeno"><strong>{{ s.prontuario }}</strong> · {{ f.dataBr(s.data_procedimento) }}</td>
            <td>{{ s.descritivo_hospital || s.xProd }} <span class="mono suave pequeno">AGHU {{ s.codigo_aghu || '—' }}</span></td>
            <td class="mono">{{ s.nLote || '—' }}</td>
            <td>—</td><td class="pequeno">não dispensado</td><td>—</td>
            <td><span :class="['etiqueta', s.situacao === 'ciente' ? 'cinza' : 'vermelho']">Usado sem dispensação{{ s.situacao === 'ciente' ? ' — farmácia ciente' : ' — sem ciência' }}</span></td>
          </tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
const q = (v: unknown) => encodeURIComponent(v == null ? '' : String(v));
</script>
