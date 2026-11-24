<template>
  <div>
    <div class="cabecalho-pagina">
      <div>
        <h1>{{ d.perfil.nome }}</h1>
        <p>{{ f.rotuloPapel(d.perfil.papel) }}<template v-if="d.perfil.setor"> · {{ d.perfil.setor }}</template></p>
      </div>
      <div class="acoes"><a class="botao secundario" href="/">Voltar</a></div>
    </div>

    <div v-if="d.modo_autenticacao === 'local'" class="cartao" style="max-width:520px">
      <h2>Alterar minha senha</h2>
      <form method="post" action="/minha-senha">
        <div class="campo"><label class="obrigatorio">Senha atual</label>
          <input type="password" name="senha_atual" required autocomplete="current-password"></div>
        <div class="campo"><label class="obrigatorio">Nova senha</label>
          <input type="password" name="nova_senha" required autocomplete="new-password">
          <div class="dica">Mínimo de 8 caracteres, com letras e números.</div></div>
        <div class="campo"><label class="obrigatorio">Confirmar nova senha</label>
          <input type="password" name="confirmar" required autocomplete="new-password"></div>
        <button class="botao">Alterar senha</button>
      </form>
    </div>
    <div v-else class="cartao" style="max-width:520px">
      <h2>Senha</h2>
      <p class="suave" style="margin:0">
        O acesso usa a sua senha de rede (Active Directory da Ebserh). Ela também vale para as
        confirmações na hora (entrega à sala, devolução, reabertura). Para trocá-la, use os canais da TI.
      </p>
    </div>

    <div class="cartao" style="max-width:520px">
      <h2>Meu acesso</h2>
      <table>
        <tbody>
          <tr><th>Usuário</th><td class="mono">{{ d.perfil.username }}</td></tr>
          <tr><th>Perfil</th><td>{{ f.rotuloPapel(d.perfil.papel) }}</td></tr>
          <tr><th>Módulos liberados</th><td>{{ (d.modulos || []).map((m: string) => f.rotuloModulo(m)).join(', ') }}</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTela } from '../../composables/useTela';

defineProps<{ d: any }>();
const { f } = useTela();
</script>
