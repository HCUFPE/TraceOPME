<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>Diagnóstico técnico</h1>
        <p>Últimas {{ d.quantidade }} linhas do log, da mais recente para a mais antiga.</p>
      </div>
      <div class="acoes">
        <a class="botao secundario" href="/admin/diagnostico?linhas=1000">Ver 1.000 linhas</a>
        <a class="botao secundario" href="/admin"> Voltar</a>
      </div>
    </div>

    <div class="aviso info">
      Este log serve para <strong>diagnosticar problema técnico</strong>. A auditoria assistencial —
      quem movimentou qual material — fica em
      <a href="/consultas/eventos">Consultas → Auditoria</a> e nunca é apagada.
      Prontuário e nome de paciente são removidos automaticamente antes da gravação, para o arquivo
      poder ser enviado ao suporte sem expor dado clínico.
      As ações de quem usa o sistema também ficam na trilha de auditoria do framework (tabela
      <span class="mono">audit_logs</span>).
    </div>

    <div class="cartao">
      <p class="suave pequeno">Arquivo: <span class="mono">{{ d.arquivo }}</span> ·
         rotaciona a cada 2 MB, mantendo as 5 versões anteriores.</p>
      <div v-if="d.linhas?.length" class="log-caixa">
        <div v-for="(linha, n) in d.linhas" :key="n"
             :class="['log-linha', linha.includes('| ERROR') ? 'erro' : (linha.includes('| WARNING') ? 'aviso' : '')]">{{ linha }}</div>
      </div>
      <p v-else class="vazio">Nenhum registro no log ainda. Boa notícia.</p>
    </div>

    <div class="cartao">
      <h2>Como ler</h2>
      <table>
        <tbody>
          <tr><th style="width:110px">ERROR</th>
              <td>Falha técnica. Nada foi gravado pela metade — a transação é desfeita.
                  Vem acompanhado do rastreamento completo do erro.</td></tr>
          <tr><th>WARNING</th>
              <td>Tentativa de login sem sucesso ou conta inativa. Várias seguidas do mesmo
                  usuário podem ser senha esquecida — ou tentativa de invasão.</td></tr>
          <tr><th>INFO</th>
              <td>Login efetuado, aplicação iniciada e bipagens recusadas por regra de negócio.
                  Recusas repetidas na mesma etapa costumam indicar necessidade de treinamento,
                  não erro do sistema.</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ d: any }>();
</script>
