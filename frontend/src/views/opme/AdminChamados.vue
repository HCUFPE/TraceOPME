<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Chamados</h1>
        <p>Problemas reportados pelos usuários (botão “Reportar problema”, no topo). Responda e mude a situação;
           quem abriu vê a resposta na própria janela de chamados.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/admin">Voltar</a></div>
    </div>

    <form method="get" action="/chamados" class="cartao" style="display:flex;gap:.6rem;align-items:flex-end;flex-wrap:wrap">
      <div class="campo" style="margin:0"><label>Situação</label>
        <select name="status">
          <option value="">todas (abertos primeiro)</option>
          <option v-for="(rot, chave) in d.situacoes" :key="chave" :value="chave" :selected="chave === d.status">{{ rot }}</option>
        </select></div>
      <button class="botao secundario">Filtrar</button>
      <span class="pequeno suave">{{ d.abertos }} aberto(s) ou em andamento</span>
    </form>

    <p v-if="!d.chamados.length" class="vazio cartao">Nenhum chamado.</p>
    <div v-for="c in d.chamados" :key="c.id_chamado" class="cartao"
         :style="`border-left:5px solid ${c.status === 'resolvido' ? '#0f766e' : c.status === 'andamento' ? '#5b7fa6' : '#b7791f'}`">
      <div class="entre" style="align-items:flex-start">
        <div style="min-width:0">
          <h3 style="margin:0">Chamado nº {{ c.id_chamado }}
            <span :class="['etiqueta', c.status === 'resolvido' ? 'verde' : c.status === 'andamento' ? 'azul' : 'amarelo']">{{ d.situacoes[c.status] }}</span></h3>
          <p class="pequeno suave" style="margin:.2rem 0 0">{{ f.dataHoraBr(c.criado_em) }} · {{ c.criado_nome }} ({{ c.criado_por }})
            <template v-if="c.pagina"> · tela <a :href="c.pagina" class="mono">{{ c.pagina }}</a></template>
            <template v-if="c.versao"> · versão {{ c.versao }}</template></p>
        </div>
      </div>
      <p style="white-space:pre-wrap;margin:.6rem 0">{{ c.descricao }}</p>
      <template v-if="c.imagem">
        <a class="pequeno" href="#" @click.prevent="aberta = aberta === c.id_chamado ? null : c.id_chamado">{{ aberta === c.id_chamado ? 'esconder imagem' : 'ver imagem anexada' }}</a>
        <ImagemApi v-if="aberta === c.id_chamado" :src="`/chamados/imagem/${c.imagem}`" alt="imagem do chamado"
                   style="display:block;max-width:100%;max-height:520px;margin:.4rem 0;border:1px solid var(--borda);border-radius:6px" />
      </template>
      <form method="post" :action="`/chamados/${c.id_chamado}/atualizar`" class="grade grade-3" style="margin-top:.6rem;align-items:end">
        <div class="campo" style="grid-column:span 2;margin:0"><label>Resposta para quem abriu</label>
          <input type="text" name="resposta" :defaultValue="c.resposta || ''" placeholder="Ex.: corrigido na versão 17.3.18"></div>
        <div style="display:flex;gap:.5rem;align-items:end">
          <div class="campo" style="margin:0;flex:1"><label>Situação</label>
            <select name="status">
              <option v-for="(rot, chave) in d.situacoes" :key="chave" :value="chave" :selected="chave === c.status">{{ rot }}</option>
            </select></div>
          <button class="botao">Salvar</button>
        </div>
      </form>
      <p v-if="c.atualizado_em" class="pequeno suave" style="margin:.4rem 0 0">Atualizado em {{ f.dataHoraBr(c.atualizado_em) }} por {{ c.atualizado_por }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import ImagemApi from '../../components/opme/ImagemApi.vue';
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
const aberta = ref<number | null>(null);
</script>
