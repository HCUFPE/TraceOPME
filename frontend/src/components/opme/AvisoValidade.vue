<template>
  <!-- nov/2026: lote com validade mais próxima no mesmo estoque. Não trava:
       a pessoa troca de lote ou dá ciência e segue (a ciência fica no histórico).
       Enter não confirma — a próxima leitura do leitor não pode dar ciência sozinha. -->
  <div id="aviso-validade" class="confirmacao-bip escolha" role="alertdialog" aria-modal="true">
    <div class="confirmacao-bip-janela" style="text-align:left">
      <div class="confirmacao-bip-icone">!</div>
      <h2>HÁ LOTE QUE VENCE ANTES</h2>
      <p class="confirmacao-bip-produto" style="text-align:center">
        <span class="mono">AGHU {{ aviso.escolhido?.aghu }}</span> · {{ aviso.escolhido?.descricao }}</p>
      <table style="margin:.6rem 0">
        <tbody>
          <tr>
            <th style="width:11rem">Você bipou</th>
            <td>lote <b class="mono">{{ aviso.escolhido?.lote }}</b> · validade <b>{{ aviso.escolhido?.validade }}</b></td>
          </tr>
          <tr style="background:var(--amarelo-claro)">
            <th>Vence antes</th>
            <td>lote <b class="mono">{{ aviso.mais_proximo?.lote }}</b> · validade <b>{{ aviso.mais_proximo?.validade_br }}</b>
              · {{ aviso.mais_proximo?.quantidade }} unidade(s) disponível(is)</td>
          </tr>
        </tbody>
      </table>
      <p style="margin:.4rem 0">O recomendado é usar primeiro o lote que vence antes. Se for seguir com o lote
        bipado, dê ciência — fica registrado no histórico do item, com o seu usuário.</p>
      <div class="linha-botoes" style="justify-content:flex-end;margin-top:.8rem">
        <button type="button" class="botao secundario" data-sem-foco="1" @click="$emit('cancelar')">
          Trocar: vou pegar o lote {{ aviso.mais_proximo?.lote }}</button>
        <button type="button" class="botao" id="aviso-validade-ciente" data-sem-foco="1" :disabled="enviando"
                @click="$emit('ciente')">Estou ciente — seguir com o lote {{ aviso.escolhido?.lote }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ aviso: any; enviando?: boolean }>(), { enviando: false });
defineEmits<{ (e: 'ciente'): void; (e: 'cancelar'): void }>();
</script>
