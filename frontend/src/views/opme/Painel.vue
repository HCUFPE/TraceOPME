<template>
  <div>
    <div v-if="d.sem_permissao" class="aviso alerta">Seu perfil não tem acesso a essa área. Fale com o administrador.</div>

    <div class="cabecalho-pagina">
      <div>
        <h1>Painel de situação</h1>
        <p>O que está parado, o que precisa da sua ação e onde está cada material agora.</p>
      </div>
    </div>

    <template v-if="p.alertas?.length">
      <h2>Alertas</h2>
      <div class="cartao" style="margin-bottom:1.75rem;border-left:5px solid var(--vermelho)">
        <p class="suave pequeno">
          Material vencido ou de lote bloqueado registrado em uso, ou saldo de empenho perto do
          limite ou esgotado. Vale olhar com atenção redobrada.
        </p>
        <div v-for="a in p.alertas" :key="a.id_alerta" style="padding:.75rem 0;border-bottom:1px solid var(--borda)">
          <div class="entre">
            <strong>{{ a.titulo }}</strong>
            <span class="suave pequeno">{{ f.dataHoraBr(a.criado_em) }}</span>
          </div>
          <p class="pequeno mono" style="margin:.3rem 0;white-space:pre-wrap">{{ a.mensagem }}</p>
          <div v-if="a.itens?.length" class="pequeno" style="margin:.3rem 0 .6rem">
            Abrir cada item:
            <template v-for="(item, i) in a.itens" :key="item.id_unidade">
              <a :href="`/consultas/item/${item.id_unidade}`">{{ item.codigo_aghu || item.xProd }}</a><template v-if="i < a.itens.length - 1"> ·</template>
            </template>
          </div>
          <div v-else-if="a.link" class="pequeno" style="margin:.3rem 0 .6rem"><a :href="a.link">Abrir</a></div>
          <form method="post" :action="`/alertas/${a.id_alerta}/resolver`" style="display:inline">
            <button class="botao secundario pequeno">Já verifiquei — marcar como resolvido</button>
          </form>
        </div>
      </div>
    </template>

    <h2>Pendências que dependem de você</h2>
    <div v-if="p.pendencias?.length" class="grade grade-3" style="margin-bottom:1.75rem">
      <a v-for="(item, i) in p.pendencias" :key="i" :class="['acao-card', item.urgencia]" :href="item.acao">
        <div class="numero">{{ item.quantidade }}</div>
        <div class="rotulo">{{ item.titulo }}</div>
        <div class="seta" style="margin-top:.5rem">Resolver agora →</div>
      </a>
    </div>
    <div v-else class="cartao">
      <p style="margin:0">Nenhuma pendência aberta para o seu perfil. Tudo em dia.</p>
    </div>

    <h2>Onde estão os materiais</h2>
    <div class="grade grade-4" style="margin-bottom:1.75rem">
      <a v-for="(bloco, i) in p.estoques" :key="i" class="acao-card" :href="bloco.link">
        <div class="numero">{{ bloco.quantidade }}</div>
        <div class="rotulo">{{ bloco.titulo }}</div>
      </a>
    </div>

    <div class="grade grade-2">
      <div class="cartao">
        <div class="entre">
          <h2>Cirurgias de hoje</h2>
          <a class="pequeno" href="/sala-procedimento/atendimentos">ver agenda completa</a>
        </div>
        <div v-if="p.cirurgias_hoje?.length" class="tabela-rolagem">
          <table>
            <thead>
              <tr><th>Unidade</th><th>Sala</th><th>Prontuário</th><th>Especialidade</th><th class="num">Usados</th></tr>
            </thead>
            <tbody>
              <tr v-for="(c, i) in p.cirurgias_hoje" :key="i">
                <td><span :class="['etiqueta', f.corUnidade(c.unidade)]">{{ f.rotuloUnidade(c.unidade) }}</span></td>
                <td><strong>{{ c.sala }}</strong></td>
                <td><a :href="`/consultas/prontuario?numero=${encodeURIComponent(c.prontuario)}`">{{ c.prontuario }}</a></td>
                <td>{{ f.especialidade(c.especialidade) }}</td>
                <td class="num">{{ c.utilizados || 0 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhum atendimento cadastrado para hoje.</p>
      </div>

      <div class="cartao">
        <div class="entre">
          <h2>Validades críticas</h2>
          <a class="pequeno" href="/consultas/validades">ver todas</a>
        </div>
        <div v-if="p.validades?.length" class="tabela-rolagem">
          <table>
            <thead><tr><th>Produto</th><th>Lote</th><th>Vence em</th><th class="num">Qtd.</th></tr></thead>
            <tbody>
              <tr v-for="(v, i) in p.validades.slice(0, 8)" :key="i">
                <td>{{ v.xProd }}</td>
                <td class="mono">{{ v.nLote || '—' }}</td>
                <td>
                  {{ f.dataBr(v.dVal) }}
                  <span v-if="v.dias_restantes !== null && v.dias_restantes !== undefined"
                        :class="['etiqueta', v.dias_restantes < 0 ? 'vermelho' : (v.dias_restantes <= 30 ? 'amarelo' : 'cinza')]">
                    {{ v.dias_restantes < 0 ? 'vencido' : `${v.dias_restantes} dias` }}
                  </span>
                </td>
                <td class="num">{{ v.quantidade }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="vazio">Nenhum item próximo do vencimento.</p>
      </div>
    </div>

    <div v-if="p.parados?.length" class="cartao">
      <h2>Itens parados em trânsito</h2>
      <p class="suave pequeno">Foram enviados mas ninguém confirmou o recebimento. Costuma ser conferência esquecida.</p>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Item</th><th>Situação</th><th>Prontuário</th><th class="num">Parado há</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(x, i) in p.parados" :key="i">
              <td>{{ x.xProd }} <span class="suave pequeno">lote {{ x.nLote || '—' }}</span></td>
              <td><span :class="['etiqueta', f.corStatus(x.status)]">{{ f.rotuloStatus(x.status) }}</span></td>
              <td>{{ x.prontuario || '—' }}</td>
              <td class="num">{{ x.dias_parado }} dia(s)</td>
              <td><a class="pequeno" :href="`/consultas/item/${x.id_unidade}`">detalhes</a></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="cartao">
      <div class="entre">
        <h2>Últimos movimentos</h2>
        <a class="pequeno" href="/consultas/eventos">ver histórico completo</a>
      </div>
      <div class="tabela-rolagem">
        <table>
          <thead><tr><th>Quando</th><th>Movimento</th><th>Item</th><th>Prontuário</th><th>Usuário</th></tr></thead>
          <tbody>
            <tr v-for="(e, i) in p.ultimos_eventos" :key="i">
              <td class="pequeno">{{ e.quando }}</td>
              <td>{{ f.movimento(e.tipo) }}</td>
              <td>{{ e.xProd || '—' }}</td>
              <td>{{ e.prontuario || '—' }}</td>
              <td class="pequeno">{{ e.usuario }}</td>
            </tr>
            <tr v-if="!p.ultimos_eventos?.length"><td colspan="5" class="vazio">Nenhum movimento registrado ainda.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const p = computed(() => props.d.painel || {});
</script>
