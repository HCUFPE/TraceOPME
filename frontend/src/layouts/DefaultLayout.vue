<template>
  <div class="relative h-screen overflow-hidden md:flex">
    <!-- Mobile Menu Header -->
    <div class="bg-paper-sidebar text-slate-700 border-b border-slate-200 flex justify-between md:hidden shrink-0 nao-imprimir">
      <router-link to="/" class="flex items-center gap-2 p-4 text-[#0C3A67] font-bold">
        <img src="/logo.svg" alt="" class="h-7 w-7 rounded-md" /> {{ SYSTEM_TITLE }}
      </router-link>
      <button @click="sidebarOpen = !sidebarOpen" class="p-4 focus:outline-none focus:bg-paper-active-link">
        <Bars3Icon class="h-6 w-6" />
      </button>
    </div>

    <!-- Sidebar (Expansível / Recolhível) -->
    <aside
      :class="[
        sidebarOpen ? 'translate-x-0' : '-translate-x-full',
        isCollapsed ? 'md:w-20' : 'md:w-64'
      ]"
      class="nao-imprimir bg-paper-sidebar text-slate-700 border-r border-slate-200 pt-7 pb-2 px-2 absolute inset-y-0 left-0 transform md:relative md:translate-x-0 transition-all duration-300 ease-in-out z-20 h-full shrink-0 flex flex-col justify-between overflow-y-auto"
    >
      <div>
        <!-- Clique na marca recolhe/expande a barra lateral -->
        <div
          @click="toggleSidebar"
          title="Clique para recolher / expandir o menu"
          class="cursor-pointer text-[#0C3A67] flex items-center space-x-3 px-3 mb-6 hover:opacity-90 transition duration-150 group"
        >
          <img src="/logo.svg" alt="" class="h-9 w-9 shrink-0 rounded-lg group-hover:scale-105 transition-transform" />
          <span v-if="!isCollapsed" class="leading-snug select-none">
            <span class="block text-xl font-extrabold">Trace<span class="text-[#0F8F7A]">OPME</span></span>
            <span class="block text-[11px] font-normal text-slate-500">Rastreabilidade de OPME</span>
          </span>
        </div>

        <div class="px-3 my-4">
          <div class="border-t border-slate-200"></div>
        </div>

        <!-- Links de Navegação (módulos liberados pelo perfil local — RBAC) -->
        <nav class="space-y-1">
          <router-link
            v-for="item in menu"
            :key="item.to"
            :to="item.to"
            :title="isCollapsed ? item.rotulo : ''"
            active-class=""
            exact-active-class=""
            :class="[isCollapsed ? 'justify-center px-2' : 'px-4', ativo(item.to) ? 'bg-paper-active-link text-[#0B5D57] font-semibold shadow-[inset_3px_0_0_#0F766E]' : 'hover:bg-slate-100 hover:text-slate-900']"
            class="flex items-center space-x-3 py-2.5 rounded transition duration-200"
          >
            <component :is="item.icone" class="h-6 w-6 shrink-0" />
            <span v-if="!isCollapsed" class="truncate">{{ item.rotulo }}</span>
          </router-link>
        </nav>
      </div>

      <!-- Rodapé de Versão da Sidebar -->
      <div v-if="!isCollapsed" class="px-4 pt-3 pb-1 border-t border-slate-200 text-xs text-slate-500 mt-6 truncate transition-opacity duration-200">
        <p class="font-semibold text-slate-700 truncate">{{ APP_NAME }}</p>
        <p class="text-[11px] text-slate-500 truncate">Versão {{ APP_VERSION }} | HC-UFPE</p>
        <p class="text-[10px] text-slate-500 truncate" :title="'Desenvolvido por ' + AUTHOR">Desenvolvido por {{ AUTHOR }}</p>
        <p class="text-[10px] text-slate-500 truncate" :title="'Suporte: ' + SUPPORT_EMAIL">Suporte:
          <a :href="`mailto:${SUPPORT_EMAIL}`" style="color:#0F766E;text-decoration:underline">{{ SUPPORT_EMAIL }}</a></p>
      </div>
      <div v-else class="px-2 pt-3 pb-1 border-t border-slate-200 text-[10px] text-center text-slate-500 mt-6">
        v{{ APP_VERSION }}
      </div>
    </aside>

    <!-- Content -->
    <div class="flex-1 flex flex-col bg-paper-bg overflow-y-auto h-full" id="conteudo-rolagem">
      <header class="nao-imprimir flex justify-between items-center px-6 py-4 bg-white/85 backdrop-blur-md border-b border-slate-200 sticky top-0 z-10">
        <!-- O título fica só no cabeçalho de cada tela (evita título repetido);
             o nome da tela continua na aba do navegador (ui.setTitulo). -->
        <div class="min-w-0"></div>
        <div class="shrink-0 flex items-center">
          <ReportarProblema v-if="authStore.isAuthenticated" />
          <router-link v-if="!authStore.isAuthenticated" to="/login">
            <Button variant="primary">
              <template #icon>
                <ArrowRightOnRectangleIcon class="h-5 w-5" />
              </template>
              Login
            </Button>
          </router-link>
          <ProfileDropdown v-else />
        </div>
      </header>
      <main class="flex-1">
        <div class="max-w-[1280px] mx-auto px-4 py-4 md:px-6 md:py-6">
          <router-view />
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import {
  HomeIcon,
  CalendarDaysIcon,
  ArchiveBoxIcon,
  BeakerIcon,
  ClipboardDocumentCheckIcon,
  BanknotesIcon,
  ClipboardDocumentListIcon,
  MagnifyingGlassIcon,
  ChartBarIcon,
  TvIcon,
  BellAlertIcon,
  Cog6ToothIcon,
  Bars3Icon,
  ArrowRightOnRectangleIcon,
} from '@heroicons/vue/24/outline';
import ProfileDropdown from '../components/ProfileDropdown.vue';
import ReportarProblema from '../components/opme/ReportarProblema.vue';
import Button from '../components/Button.vue';
import { useAuthStore } from '../stores/auth';
import { APP_VERSION, APP_NAME, SYSTEM_TITLE, AUTHOR, SUPPORT_EMAIL } from '../config/version';

const sidebarOpen = ref(false);
const isCollapsed = ref(false);

const route = useRoute();
const authStore = useAuthStore();

// Módulos na ordem do menu da v17. Só aparecem os liberados para o perfil.
const MODULOS = [
  { modulo: 'painel', to: '/', rotulo: 'Painel', icone: HomeIcon },
  { modulo: 'procedimentos', to: '/procedimentos', rotulo: 'Procedimentos', icone: CalendarDaysIcon },
  { modulo: 'almoxarifado', to: '/almoxarifado', rotulo: 'Almoxarifado', icone: ArchiveBoxIcon },
  { modulo: 'farmacia', to: '/farmacia', rotulo: 'Farmácia', icone: BeakerIcon },
  { modulo: 'sala-procedimento', to: '/sala-procedimento', rotulo: 'Sala de procedimento', icone: ClipboardDocumentCheckIcon },
  { modulo: 'monitoramento', to: '/monitoramento', rotulo: 'Central das salas', icone: TvIcon },
  { modulo: 'qg', to: '/qg', rotulo: 'QG da enfermagem', icone: BellAlertIcon },
  { modulo: 'consignados', to: '/consignados', rotulo: 'Consignados', icone: BanknotesIcon },
  { modulo: 'inventario', to: '/inventario', rotulo: 'Inventário', icone: ClipboardDocumentListIcon },
  { modulo: 'consultas', to: '/consultas', rotulo: 'Consultas', icone: MagnifyingGlassIcon },
  { modulo: 'indicadores', to: '/indicadores', rotulo: 'Indicadores', icone: ChartBarIcon },
  { modulo: 'admin', to: '/admin', rotulo: 'Administração', icone: Cog6ToothIcon },
];

const menu = computed(() => MODULOS.filter((m) => m.modulo === 'painel' || authStore.podeAcessar(m.modulo)));

function ativo(destino: string) {
  if (destino === '/') return route.path === '/';
  return route.path === destino || route.path.startsWith(destino + '/');
}

const toggleSidebar = () => {
  isCollapsed.value = !isCollapsed.value;
};

// Close mobile sidebar on route change
watch(() => route.path, () => {
  sidebarOpen.value = false;
});
</script>
