<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Estornar uso registrado</h1>
        <p>Por paciente: busque pelo prontuário ou pelo dia/período, abra a ficha e estorne o implante
           bipado no paciente errado, em duplicidade, ou que acabou não sendo utilizado.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/sala-procedimento">Voltar</a></div>
    </div>

    <div class="aviso info">
      <strong>Nada é apagado.</strong> O registro original continua no histórico do item, marcado
      como estornado, com o motivo e o nome de quem estornou. É assim que precisa ser: em
      rastreabilidade de implante, apagar registro é pior do que o erro que se quer corrigir.
    </div>

    <!-- v18: o estorno é por paciente — primeiro a lista, depois a ficha -->
    <template v-if="!d.ficha">
      <form method="get" action="/sala-procedimento/estorno" class="cartao">
        <div class="filtros">
          <div class="campo" style="flex:1 1 220px">
            <label>Prontuário</label>
            <input type="text" name="prontuario" :defaultValue="d.prontuario" inputmode="numeric" autofocus
                   placeholder="deixe em branco para ver todos do período">
          </div>
          <div class="campo"><label>De</label><input type="date" name="inicio" :defaultValue="d.inicio"></div>
          <div class="campo"><label>Até</label><input type="date" name="fim" :defaultValue="d.fim"></div>
          <button class="botao">Buscar</button>
        </div>
      </form>

      <div class="cartao">
        <h2>{{ d.pacientes.length }} paciente(s) com implante registrado
          <span class="pequeno suave"><template v-if="d.prontuario">· prontuário {{ d.prontuario }}</template>
            <template v-if="d.inicio"> · {{ f.dataBr(d.inicio) }} a {{ f.dataBr(d.fim) }}</template></span></h2>
        <div v-if="d.pacientes.length" class="tabela-rolagem">
          <table>
            <thead><tr><th>Data</th><th>Prontuário</th><th>Paciente</th><th>Local</th><th>Especialidade</th>
                       <th class="num">Implantes</th><th>Situação</th><th></th></tr></thead>
            <tbody>
              <tr v-for="p in d.pacientes" :key="p.id_atendimento">
                <td>{{ f.dataBr(p.data) }}<span v-if="p.hora_inicio" class="pequeno suave"> {{ p.hora_inicio }}</span></td>
                <td class="mono"><strong>{{ p.prontuario }}</strong></td>
                <td>{{ p.paciente || '—' }}</td>
                <td>{{ f.rotuloUnidade(p.unidade) }}<template v-if="p.sala"> — sala {{ p.sala }}</template></td>
                <td>{{ f.especialidade(p.especialidade) }}</td>
                <td class="num">{{ p.usados }}</td>
                <td><span :class="['etiqueta', p.status === 'aberto' ? 'azul' : 'cinza']">{{ p.status === 'aberto' ? 'em andamento' : p.status }}</span></td>
                <td><a class="botao pequeno" :href="`/sala-procedimento/estorno?atendimento=${p.id_atendimento}`">Abrir ficha</a></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhum implante registrado com esses filtros.</p>
      </div>
    </template>

    <template v-else>
      <div class="cartao" style="border-left:5px solid var(--azul)">
        <div class="entre" style="flex-wrap:wrap;gap:.6rem">
          <div>
            <h2 style="margin:0">Prontuário {{ d.ficha.prontuario }}<template v-if="d.ficha.paciente"> · {{ d.ficha.paciente }}</template></h2>
            <p class="pequeno" style="margin:.2rem 0 0">{{ f.rotuloUnidade(d.ficha.unidade) }}<template v-if="d.ficha.sala"> — sala {{ d.ficha.sala }}</template>
              · {{ f.especialidade(d.ficha.especialidade) }} · {{ f.dataBr(d.ficha.data_procedimento) }}
              · <span :class="['etiqueta', d.ficha.status === 'aberto' ? 'azul' : 'cinza']">{{ d.ficha.status === 'aberto' ? 'em andamento' : d.ficha.status }}</span></p>
          </div>
          <a class="botao secundario" href="/sala-procedimento/estorno">Outro paciente</a>
        </div>
        <p class="pequeno suave" style="margin:.6rem 0 0">“Voltar para a farmácia” não cai direto no estoque: o item fica aguardando a
          farmácia dar ciência de que voltou (Farmácia → Não utilizados — dar ciência). Vale também com o procedimento encerrado.</p>
      </div>

      <div class="cartao">
        <h2>Implantes registrados neste paciente ({{ d.usos.length }})</h2>
        <template v-if="d.usos.length">
          <details v-for="u in d.usos" :key="u.id_unidade" style="border-bottom:1px solid var(--borda);padding:.75rem 0">
            <summary style="cursor:pointer">
              <strong>{{ u.xProd }}</strong>
              <span class="suave pequeno">
                lote {{ u.nLote || '—' }} · val. {{ f.dataBr(u.dVal) || '—' }}
                <template v-if="u.numero_serie"> · série {{ u.numero_serie }}</template>
              </span><br>
              <span class="pequeno">registrado em {{ f.dataHoraBr(u.data_evento) }} por {{ u.usuario || '—' }}</span>
            </summary>
            <form method="post" :action="`/sala-procedimento/estorno/${u.id_unidade}`"
                  style="margin-top:.9rem;padding-left:1rem;border-left:3px solid var(--vermelho)"
                  data-confirmar="Confirma o estorno deste implante? A ação fica registrada na auditoria.">
              <div class="grade grade-2">
                <div class="campo">
                  <label class="obrigatorio">Para onde vai o material?</label>
                  <select name="destino">
                    <option v-for="(texto, codigo) in d.destinos" :key="codigo" :value="codigo">{{ texto }}</option>
                  </select>
                </div>
                <div class="campo">
                  <label class="obrigatorio">Motivo do estorno</label>
                  <input type="text" name="motivo" required minlength="10"
                         placeholder="Ex.: bipado em duplicidade / no prontuário errado (o correto é 123456)">
                  <div class="dica">Mínimo de 10 caracteres. Será lido em auditoria.</div>
                </div>
              </div>
              <div class="linha-botoes">
                <button class="botao perigo">Estornar este uso</button>
                <a class="botao secundario" :href="`/consultas/item/${u.id_unidade}`"> Ver histórico</a>
              </div>
            </form>
          </details>
        </template>
        <p v-else class="vazio">Nenhum implante registrado (ou todos já estornados) neste paciente.</p>
      </div>
    </template>

    <div v-if="d.recentes?.length" class="cartao">
      <h2>Estornos recentes</h2>
      <p class="suave pequeno">Volume alto aqui costuma indicar bipagem apressada na sala.</p>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Quando</th><th>Item</th><th>Prontuário</th>
                     <th>Destino</th><th>Motivo</th><th>Quem</th></tr></thead>
          <tbody>
            <tr v-for="(r, n) in d.recentes" :key="n">
              <td class="pequeno">{{ f.dataHoraBr(r.data_evento) }}</td>
              <td><a :href="`/consultas/item/${r.id_unidade}`">{{ r.xProd || r.id_unidade }}</a>
                  <span class="suave pequeno"> lote {{ r.nLote || '—' }}</span></td>
              <td>{{ r.prontuario || '—' }}</td>
              <td><span :class="['etiqueta', f.corStatus(r.status_novo)]">{{ f.rotuloStatus(r.status_novo) }}</span></td>
              <td class="pequeno">{{ r.motivo }}</td>
              <td class="pequeno">{{ r.usuario }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
