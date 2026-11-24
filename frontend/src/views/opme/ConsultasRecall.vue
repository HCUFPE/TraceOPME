<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Recall — bloqueio de lote</h1>
        <p>Bloqueie um lote e o sistema passa a recusar qualquer movimentação dele em
           direção ao paciente, em todas as áreas, na mesma hora.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/consultas">Voltar</a></div>
    </div>

    <form method="post" action="/consultas/recall" class="cartao"
          data-confirmar="Bloquear este lote? Ninguém conseguirá movimentá-lo até a liberação.">
      <h2>Bloquear um lote</h2>
      <div class="grade grade-2">
        <div class="campo">
          <label class="obrigatorio">Lote</label>
          <input type="text" name="nLote" required placeholder="como está na embalagem">
        </div>
        <div class="campo">
          <label>Código AGHU <span class="opcional">(opcional)</span></label>
          <input type="text" name="codigo_aghu">
          <div class="dica">
            Em branco, bloqueia o lote em qualquer produto — é o mais seguro quando o
            comunicado do fornecedor cita só o lote.
          </div>
        </div>
        <div class="campo">
          <label>Fornecedor <span class="opcional">(opcional)</span></label>
          <input type="text" name="fornecedor">
        </div>
        <div class="campo">
          <label>Referência <span class="opcional">(nº do comunicado, ofício, alerta)</span></label>
          <input type="text" name="referencia">
        </div>
      </div>
      <div class="campo">
        <label class="obrigatorio">Motivo</label>
        <input type="text" name="motivo" required
               placeholder="Ex.: recall do fornecedor por falha de esterilização — comunicado 12/2026">
        <div class="dica">Este texto aparece para quem tentar bipar o material.</div>
      </div>
      <button class="botao perigo">Bloquear lote</button>
    </form>

    <div class="cartao">
      <h2>Lotes bloqueados</h2>
      <div v-if="d.bloqueios?.length" class="tabela-rolagem">
        <table>
          <thead>
            <tr><th>Lote</th><th>AGHU</th><th>Motivo</th>
                <th class="num">Em circulação</th><th class="num">Já implantadas</th>
                <th>Situação</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="b in d.bloqueios" :key="b.id_bloqueio">
              <td class="mono"><strong>{{ b.nLote }}</strong></td>
              <td class="mono pequeno">{{ b.codigo_aghu || 'todos' }}</td>
              <td class="pequeno">{{ b.motivo }}</td>
              <td class="num"><span v-if="b.em_circulacao" class="etiqueta vermelho">{{ b.em_circulacao }}</span><template v-else>0</template></td>
              <td class="num"><span v-if="b.implantadas" class="etiqueta amarelo">{{ b.implantadas }}</span><template v-else>0</template></td>
              <td><span :class="['etiqueta', b.status === 'ativo' ? 'vermelho' : 'cinza']">{{ b.status === 'ativo' ? 'Bloqueado' : 'Liberado' }}</span></td>
              <td><a class="botao pequeno secundario" :href="`/consultas/recall/${b.id_bloqueio}`">Abrir</a></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhum lote bloqueado. É assim que se espera que fique.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ d: any }>();
</script>
