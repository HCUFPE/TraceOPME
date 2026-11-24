import { createRouter, createWebHistory, NavigationGuardNext, RouteLocationNormalized } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import { useAvisoStore } from '../stores/aviso';
import Login from '../views/Login.vue';
import PaginaOpme from '../views/PaginaOpme.vue';

/**
 * Rotas do TraceOPME.
 *
 * As telas mantêm exatamente os endereços da v17 (/almoxarifado/nf/123,
 * /bipagem/registrar_uso?atendimento=..., etc.). Todas passam pela PaginaOpme,
 * que busca os dados em /api + o mesmo endereço e escolhe a view pela "tela"
 * devolvida pelo backend (ver views/opme/telas.ts). Assim, redirecionamentos e
 * links internos continuam valendo como antes.
 */
const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { layout: 'LoginLayout' },
  },
  {
    path: '/:caminho(.*)*',
    name: 'TraceOPME',
    component: PaginaOpme,
    meta: { requiresAuth: true },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  linkActiveClass: 'bg-paper-active-link',
  linkExactActiveClass: 'bg-paper-active-link',
  scrollBehavior(to, from) {
    if (to.hash) return false; // a própria tela rola até a âncora depois de carregar
    if (to.path !== from.path) {
      const area = document.getElementById('conteudo-rolagem');
      if (area) area.scrollTop = 0;
      return { top: 0 };
    }
    return false;
  },
});

router.beforeEach(async (to: RouteLocationNormalized, _from, next: NavigationGuardNext) => {
  // Pinia store must be used inside a function to ensure it's initialized
  const authStore = useAuthStore();
  if (!authStore.pronto) await authStore.initializeAuth();

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'Login', query: to.fullPath !== '/' ? { proximo: to.fullPath } : {} });
  } else if (to.name === 'Login' && authStore.isAuthenticated) {
    next('/');
  } else {
    next();
  }
});

router.afterEach((to, from) => {
  if (to.path !== from.path || to.fullPath.split('#')[0] !== from.fullPath.split('#')[0]) {
    useAvisoStore().aoNavegar();
  }
});

export default router;
