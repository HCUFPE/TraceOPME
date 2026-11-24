<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Inventário</h1>
        <p>Contagem periódica do estoque: bipe material atrás de material e, no fim,
           o sistema mostra o que não fecha.</p>
      </div>
    </div>

    <div class="cartao">
      <h2>Começar uma contagem</h2>
      <p class="suave pequeno">
        Cada contagem cobre um estoque só: o <strong>almoxarifado</strong>, a <strong>Farmácia do Bloco
        Cirúrgico</strong> ou a <strong>Farmácia da Hemodinâmica</strong>. Escolha o local onde você está.
        No almoxarifado, material em divergência também entra, porque continua fisicamente na prateleira.
      </p>
      <form method="post" action="/inventario/novo">
        <div class="filtros">
          <div class="campo">
            <label class="obrigatorio">Local a contar</label>
            <select name="local">
              <option value="">— escolha o local —</option>
              <option v-for="(nome, chave) in d.locais" :key="chave" :value="chave" :selected="d.local_sugerido === chave">{{ nome }} — {{ d.esperado?.[chave] ?? 0 }} unidade(s) no sistema</option>
            </select>
          </div>
          <div class="campo">
            <label>Observação <span class="opcional">(opcional)</span></label>
            <input type="text" name="observacao" placeholder="ex.: contagem mensal de setembro">
          </div>
          <button class="botao">Abrir contagem</button>
        </div>
      </form>
    </div>

    <div class="cartao" style="margin-top:1.5rem">
      <h2>Contagens anteriores</h2>
      <div v-if="d.contagens?.length" class="tabela-rolagem">
        <table>
          <thead>
            <tr><th>Contagem</th><th>Local</th><th>Situação</th><th class="num">Leituras</th>
                <th>Aberta por</th><th>Encerrada</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="c in d.contagens" :key="c.id_inventario">
              <td class="mono">{{ c.id_inventario }}
                <div v-if="c.observacao" class="pequeno suave">{{ c.observacao }}</div></td>
              <td>{{ c.local_rotulo }}</td>
              <td><span v-if="c.status === 'aberto'" class="etiqueta amarelo">em contagem</span>
                  <span v-else class="etiqueta cinza">encerrada</span></td>
              <td class="num">{{ c.leituras }}</td>
              <td class="pequeno">{{ c.criado_por }}
                <div class="suave">{{ f.dataHoraBr(c.criado_em) }}</div></td>
              <td class="pequeno suave">{{ c.encerrado_em ? f.dataHoraBr(c.encerrado_em) : '—' }}</td>
              <td>
                <a v-if="c.status === 'aberto'" class="botao pequeno" :href="`/inventario/${c.id_inventario}`">Continuar</a>
                <a v-else class="botao secundario pequeno" :href="`/inventario/${c.id_inventario}/relatorio`">Ver relatório</a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="vazio">Nenhuma contagem registrada ainda.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
