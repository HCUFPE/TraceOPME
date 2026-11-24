<template>
  <component :is="layout">
    <router-view />
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import DefaultLayout from './layouts/DefaultLayout.vue';
import LoginLayout from './layouts/LoginLayout.vue';

const route = useRoute();

// A autenticação é inicializada pelo guarda do roteador (router/index.ts),
// antes da primeira tela, para o cookie de "lembrar de mim" valer no F5.
const layout = computed(() => {
  return route.meta.layout === 'LoginLayout' ? LoginLayout : DefaultLayout;
});
</script>
