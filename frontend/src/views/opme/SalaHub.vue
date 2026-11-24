<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Sala de procedimento</h1>
      </div>
    </div>

    <EscolhaUnidade :unidade-atual="d.unidade_atual" :unidades="d.unidades" />

    <div class="grade grade-3">
      <!-- v18.3: o fluxo da sala começa aqui — abrir a sala e, em seguida, dar ciência do material. -->
      <a class="acao-card cor-azul alta" href="/sala-procedimento/salas">
        <h3>Abrir sala</h3>
        <div class="numero">{{ d.salas_abertas ?? 0 }}</div>
        <p class="rotulo">sala(s) aberta(s) agora</p>
      </a>
      <a v-if="d.disp_pendentes?.length" class="acao-card cor-verde alta" href="/sala-procedimento/atendimentos">
        <h3>Confirmar recebimento da farmácia</h3>
        <div class="numero">{{ d.disp_pendentes.length }}</div>
        <p class="rotulo">aguardando a sala</p>
      </a>
      <a v-if="d.nao_recebidos?.length" class="acao-card alta" href="/sala-procedimento/atendimentos#nao-recebidos">
        <h3>Conferir: a farmácia não recebeu de volta</h3>
        <div class="numero">{{ d.nao_recebidos.length }}</div>
        <p class="rotulo">Bipar o uso ou devolver.</p>
      </a>
      <a class="acao-card cor-verde" href="/sala-procedimento/atendimentos">
        <h3>Solicitar OPME à farmácia</h3>
        <p class="rotulo">Pedir OPME para o paciente.</p>
      </a>
      <a :class="['acao-card', 'cor-roxo', { alta: d.caixas_sala.enviadas || d.caixas_sala.fora_do_prazo || d.caixas_sala.divergentes }]" href="/sala-procedimento/caixas">
        <h3>Caixas na sala</h3>
        <div class="numero">{{ d.caixas_sala.na_sala }}</div>
        <p class="rotulo">caixa(s) de consignado na sala<template v-if="d.caixas_sala.enviadas"> · <strong>{{ d.caixas_sala.enviadas }} chegando — dar ciência</strong></template><template v-if="d.caixas_sala.fora_do_prazo"> · <strong>{{ d.caixas_sala.fora_do_prazo }} fora do prazo (devolver até 23:59)</strong></template><template v-if="d.caixas_sala.divergentes"> · <strong>{{ d.caixas_sala.divergentes }} com pendência</strong></template>.</p>
      </a>
      <a class="acao-card cor-verde" href="/sala-procedimento/atendimentos?operacao=registrar_uso">
        <h3>Registrar uso no paciente</h3>
        <p class="rotulo">Bipar no momento do uso.</p>
      </a>
      <a class="acao-card cor-azul" href="/procedimentos">
        <h3>Procedimentos do dia</h3>
        <div class="numero">{{ d.cirurgias }}</div>
        <p class="rotulo">cirurgias com OPME hoje<template v-if="d.unidade_atual"> em {{ d.unidades[d.unidade_atual]?.rotulo }}</template></p>
      </a>
      <a class="acao-card cor-azul" href="/consultas/prontuario">
        <h3>Consultar por prontuário</h3>
        <p class="rotulo">Implantes com lote e validade.</p>
      </a>
      <a class="acao-card cor-amarelo" href="/sala-procedimento/estorno">
        <h3>Estornar uso registrado</h3>
        <p class="rotulo">Paciente errado ou duplicidade.</p>
      </a>
    </div>
  </div>
</template>

<script setup lang="ts">
import EscolhaUnidade from '../../components/opme/EscolhaUnidade.vue';

defineProps<{ d: any }>();
</script>
