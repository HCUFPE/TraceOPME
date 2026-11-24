import { createApp } from 'vue'
import { createPinia } from 'pinia'
// v18.12: fonte Nunito dentro da aplicação (antes vinha do Google Fonts — sem internet
// no computador do hospital a tela demorava a aparecer)
import '@fontsource/nunito/400.css'
import '@fontsource/nunito/600.css'
import '@fontsource/nunito/700.css'
import './index.css'
import './assets/opme.css'
// v18.17.2: depois que o servidor é atualizado, o navegador que ficou com a
// página antiga aberta pede pedaços de tela (JS/CSS) que não existem mais no
// servidor. A tela então abre "desregulada": texto solto, rótulos cortados e
// botões por cima uns dos outros. Quando isso acontece, recarrega sozinha uma
// vez (a trava no sessionStorage evita ficar recarregando em loop).
window.addEventListener('vite:preloadError', () => {
  if (sessionStorage.getItem('recarregou-por-versao-nova')) return
  try { sessionStorage.setItem('recarregou-por-versao-nova', '1') } catch { /* sem storage */ }
  window.location.reload()
})

import App from './App.vue'
import router from './router'

import Toast from 'vue-toastification';
import 'vue-toastification/dist/index.css';

const app = createApp(App);

app.use(createPinia());
app.use(router);
app.use(Toast);
app.mount('#app')
