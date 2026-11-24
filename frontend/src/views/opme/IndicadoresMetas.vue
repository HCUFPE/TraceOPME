<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Metas dos indicadores</h1>
        <p>Defina o que é aceitável em cada indicador. Os valores sugeridos são um ponto de partida —
           ajuste depois de um ou dois meses, quando houver base histórica do serviço.</p>
      </div>
    </div>

    <AbasIndicadores :unidade="d.unidade" atual="metas" :inicio="f.hojeIso()" :fim="f.hojeIso()" />

    <div class="aviso info">
      <strong>Como funciona o semáforo.</strong>
      Em indicadores do tipo “quanto maior melhor”, fica verde a partir da meta, amarelo a partir do
      limite de atenção e vermelho abaixo dele. Nos do tipo “quanto menor melhor”, é o inverso.
      Salvar com os dois campos <strong>em branco</strong> desliga o semáforo daquele indicador —
      ele passa a ser só acompanhamento. Para voltar ao valor que sugeri, use
      <strong>“Voltar ao sugerido”</strong>.
    </div>

    <div v-for="(dados, chave) in d.grupos" :key="chave" class="cartao">
      <h2>{{ dados[0] }}</h2>
      <p class="suave pequeno">{{ dados[1] }}</p>

      <div class="tabela-rolagem">
        <table>
          <thead>
            <tr><th style="min-width:220px">Indicador</th><th>Sentido</th>
                <th class="num" style="width:120px">Meta</th>
                <th class="num" style="width:120px">Atenção</th>
                <th style="width:200px">Ações</th></tr>
          </thead>
          <tbody>
            <tr v-for="ind in d.por_grupo?.[chave] || []" :key="ind.codigo">
              <td>
                <!-- O formulário mora aqui, mas os campos ficam nas outras células
                     ligados pelo atributo form= — assim o HTML da tabela continua válido. -->
                <form method="post" :action="`/indicadores/metas/${ind.codigo}`" :id="`meta-${ind.codigo}`"></form>
                <strong>{{ ind.nome }}</strong>
                <div class="suave pequeno">{{ ind.pergunta }}</div>
                <details class="pequeno" style="margin-top:.25rem">
                  <summary style="cursor:pointer;color:var(--azul)">como é calculado</summary>
                  <div style="margin-top:.35rem">{{ ind.formula }}</div>
                  <div class="suave" style="margin-top:.35rem">{{ ind.por_que }}</div>
                </details>
              </td>
              <td class="pequeno">
                <span v-if="ind.direcao === 'maior'" class="etiqueta verde">quanto maior, melhor</span>
                <span v-else-if="ind.direcao === 'menor'" class="etiqueta azul">quanto menor, melhor</span>
                <span v-else class="etiqueta cinza">acompanhamento</span>
                <div class="suave" style="margin-top:.25rem">unidade: {{ ind.unidade }}</div>
              </td>
              <td class="num">
                <input type="text" name="meta" inputmode="decimal" style="text-align:right"
                       :form="`meta-${ind.codigo}`" :defaultValue="valor(cfg(ind).meta)">
              </td>
              <td class="num">
                <input type="text" name="atencao" inputmode="decimal" style="text-align:right"
                       :form="`meta-${ind.codigo}`" :defaultValue="valor(cfg(ind).atencao)">
              </td>
              <td>
                <div style="display:flex;gap:.4rem;flex-wrap:wrap">
                  <button class="botao pequeno" :form="`meta-${ind.codigo}`" name="acao" value="salvar">Salvar</button>
                  <button v-if="cfg(ind).personalizada" class="botao pequeno secundario" :form="`meta-${ind.codigo}`"
                          name="acao" value="restaurar">Voltar ao sugerido</button>
                </div>
                <div v-if="cfg(ind).personalizada && cfg(ind).atualizado_por" class="suave pequeno" style="margin-top:.3rem">
                  ajustada por {{ cfg(ind).atualizado_por }} em {{ f.dataHoraBr(cfg(ind).atualizado_em) }}
                </div>
                <div v-else class="suave pequeno" style="margin-top:.3rem">valor sugerido</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import AbasIndicadores from '../../components/opme/indicadores/AbasIndicadores.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const cfg = (ind: any) => props.d.config?.[ind.codigo] || {};
const valor = (v: unknown) => (v === null || v === undefined ? '' : String(v));
</script>
