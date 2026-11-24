<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Caixas na sala</h1>
        <p>A caixa de consignado fica na sala o dia todo. Dê ciência da <strong>caixa</strong> quando ela chegar, bipe a
           caixa e o item usado em cada paciente (Registrar uso) e devolva a caixa à farmácia até as <strong>23:59</strong>.</p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/sala-procedimento">Voltar</a></div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" />

    <form v-if="d.chegando?.length" method="post" action="/sala-procedimento/caixas/receber" class="cartao" id="form-cx"
          style="border-left:5px solid var(--verde)" @submit="validar">
      <h2>Chegaram — dar ciência da caixa ({{ d.chegando.length }})</h2>
      <p class="pequeno suave">Marque a caixa que chegou ou bipe o código dela. Não precisa conferir item a item.</p>
      <input type="text" id="bip-cx" ref="campoBip" v-model="codigo" autocomplete="off" placeholder="bipe a caixa (CX-…)"
             style="font-size:1.2rem;max-width:22rem" @keydown.enter.prevent="bipar">
      <span class="pequeno" :style="{ color: res.ok ? 'var(--verde)' : 'var(--vermelho)' }"> {{ res.texto }}</span>
      <div class="tabela-rolagem" style="margin-top:.6rem"><table>
        <thead><tr><th>Chegou?</th><th>Caixa</th><th>Sala</th><th class="num">Itens</th><th>Enviada</th></tr></thead>
        <tbody>
          <tr v-for="t in d.chegando" :key="t.id_turno" :style="marcadosPorBip.includes(t.id_turno) ? 'background:var(--verde-claro)' : ''">
            <td><input type="checkbox" name="turno" :value="t.id_turno" v-model="marcados" style="width:1.4rem;height:1.4rem"></td>
            <td class="mono"><strong>{{ t.id_caixa }}</strong><br><span class="pequeno suave">{{ t.nome_caixa }}</span></td>
            <td>{{ t.local }}</td><td class="num">{{ t.qtd_enviada }}</td>
            <td class="pequeno">{{ f.dataHoraBr(t.enviada_em) }} · {{ t.enviada_por }}</td>
          </tr>
        </tbody>
      </table></div>
      <template v-if="d.pode_dar_ciencia">
        <p class="pequeno">Fica registrado em nome de <strong>{{ d.nome_logado }}</strong> (usuário logado).</p>
        <button class="botao">Dar ciência da caixa</button>
      </template>
      <p v-else class="aviso alerta" style="margin:0">Quem dá ciência é a sala de procedimento.</p>
    </form>

    <div v-for="([t, faltam], n) in d.pendencias" :key="n" class="cartao" style="border-left:5px solid var(--vermelho)">
      <h2>Pendência: a caixa {{ t.id_caixa }} voltou faltando {{ faltam.length }} item(ns)</h2>
      <p class="pequeno">{{ t.local }} · dia {{ f.dataBr(t.data) }}. Se o item foi usado e não foi bipado, vá em
        <a href="/sala-procedimento/atendimentos?operacao=registrar_uso">Registrar uso</a>, abra o paciente certo, bipe a caixa
        <strong>{{ t.id_caixa }}</strong> e o item. Se não foi usado, avise a farmácia.</p>
      <div class="tabela-rolagem"><table>
        <thead><tr><th>Material</th><th>AGHU</th><th>Lote</th><th>Validade</th><th>Série</th></tr></thead>
        <tbody><tr v-for="(i, k) in faltam" :key="k"><td>{{ i.produto }}</td><td class="mono pequeno">{{ i.codigo_aghu || '—' }}</td>
          <td class="mono">{{ i.nLote || '—' }}</td><td>{{ f.dataBr(i.dVal) || '—' }}</td><td class="mono pequeno">{{ i.numero_serie || '—' }}</td></tr></tbody>
      </table></div>
    </div>

    <div class="cartao">
      <h2>Na sala ({{ d.na_sala.length }})</h2>
      <div v-if="d.na_sala.length" class="tabela-rolagem"><table>
        <thead><tr><th>Caixa</th><th>Sala</th><th class="num">Enviados</th><th class="num">Usados</th><th class="num">Na caixa</th><th>Prazo</th><th></th></tr></thead>
        <tbody>
          <tr v-for="t in d.na_sala" :key="t.id_turno" :style="t.fora_do_prazo ? 'background:var(--vermelho-claro)' : ''">
            <td class="mono"><strong>{{ t.id_caixa }}</strong><br><span class="pequeno suave">{{ t.nome_caixa }}</span></td>
            <td>{{ t.local }}</td><td class="num">{{ t.qtd_enviada }}</td><td class="num">{{ t.usados }}</td><td class="num"><strong>{{ t.restam }}</strong></td>
            <td class="pequeno"><template v-if="t.fora_do_prazo"><strong style="color:var(--vermelho)">FORA DO PRAZO</strong><br></template>devolver até {{ f.dataHoraBr(t.prazo) }}</td>
            <td><form v-if="d.pode_dar_ciencia" method="post" :action="`/sala-procedimento/caixas/${t.id_turno}/devolver`"
                    :data-confirmar="`Devolver a caixa ${t.id_caixa} à farmácia com ${t.restam} item(ns)? Depois disso ela não pode mais ser usada hoje.`">
                <button class="botao pequeno">Devolver à farmácia</button></form></td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="vazio">Nenhuma caixa na sala agora.</p>
    </div>

    <div v-if="d.devolvidas?.length" class="cartao">
      <h2>Devolvidas — aguardando a conferência da farmácia</h2>
      <ul class="lista"><li v-for="t in d.devolvidas" :key="t.id_turno"><span class="mono">{{ t.id_caixa }}</span> · {{ t.local }} · {{ t.restam }} item(ns) ·
        devolvida por {{ t.devolvida_nome }} em {{ f.dataHoraBr(t.devolvida_em) }}</li></ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';
import { useTela } from '../../composables/useTela';

const props = defineProps<{ d: any }>();
const { f } = useTela();
const marcados = ref<string[]>([]);
const marcadosPorBip = ref<string[]>([]);
const codigo = ref('');
const res = ref({ ok: true, texto: '' });
const campoBip = ref<HTMLInputElement | null>(null);
onMounted(() => campoBip.value?.focus());

function bipar() {
  const c = codigo.value.trim().toUpperCase();
  codigo.value = '';
  const t = (props.d.chegando || []).find((x: any) => String(x.id_caixa).toUpperCase() === c);
  if (t) {
    if (!marcados.value.includes(t.id_turno)) marcados.value.push(t.id_turno);
    if (!marcadosPorBip.value.includes(t.id_turno)) marcadosPorBip.value.push(t.id_turno);
    res.value = { ok: true, texto: `✔ ${c} marcada.` };
  } else {
    res.value = { ok: false, texto: `✖ ${c} não está chegando para esta unidade.` };
  }
}

function validar(e: Event) {
  if (!marcados.value.length) { e.preventDefault(); alert('Marque ou bipe a caixa que chegou.'); }
}
</script>
