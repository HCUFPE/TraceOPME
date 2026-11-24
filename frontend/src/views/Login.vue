<template>
  <div class="w-full max-w-md px-4 py-8 opme">
    <div class="login-logo">
      <img src="/logo.svg" alt="" width="84" height="84">
      <h1>Trace<span class="marca-destaque">OPME</span></h1>
    </div>
    <p class="text-center text-slate-600 text-sm" style="margin-top:-.25rem;margin-bottom:1rem">{{ SUBTITLE }}</p>

    <Card>
      <div class="abas">
        <button type="button" :class="{ ativa: aba === 'entrar' }" @click="trocar('entrar')">Entrar</button>
        <button v-if="modo === 'local'" type="button" :class="{ ativa: aba === 'cadastro' }" @click="trocar('cadastro')">Solicitar acesso</button>
        <button v-if="modo === 'local'" type="button" :class="{ ativa: aba === 'senha' }" @click="trocar('senha')">Esqueci a senha</button>
      </div>

      <div v-if="mensagem" :class="['aviso', mensagem.tipo || (mensagem.ok ? 'sucesso' : 'erro')]">{{ mensagem.texto }}</div>

      <!-- Entrar -->
      <form v-if="aba === 'entrar'" @submit.prevent="handleLogin">
        <div class="campo">
          <label for="username">Usuário</label>
          <input v-model="username" id="username" type="text" autocomplete="username" autofocus required
                 :placeholder="modo === 'ad' ? 'seu login de rede (EBSERHNET)' : ''">
        </div>
        <div class="campo">
          <label for="password">Senha</label>
          <div class="relative">
            <input v-model="password" id="password" :type="passwordFieldType" autocomplete="current-password" required
                   style="padding-right:2.6rem">
            <button type="button" @click="passwordVisible = !passwordVisible"
                    class="absolute inset-y-0 right-0 px-3 flex items-center text-gray-500" tabindex="-1">
              <component :is="passwordFieldType === 'password' ? EyeIcon : EyeSlashIcon" class="h-5 w-5" />
            </button>
          </div>
          <div v-if="modo === 'ad'" class="dica">Use o mesmo login e senha da rede.
            No primeiro acesso, se você ainda não tiver perfil, o pedido de acesso será liberado pelo administrador.</div>
        </div>
        <div class="campo">
          <label class="flex items-center" style="font-weight:400">
            <input type="checkbox" v-model="rememberMe">
            <span class="ml-2 text-sm">Lembrar de mim</span>
          </label>
        </div>
        <button class="botao" style="width:100%" :disabled="loading">
          <ArrowRightOnRectangleIcon class="h-5 w-5" /> Entrar
        </button>
      </form>

      <!-- Solicitar acesso -->
      <form v-else-if="aba === 'cadastro'" @submit.prevent="enviar('/api/solicitar-cadastro', $event)">
        <div class="campo">
          <label :class="{ obrigatorio: modo === 'local' }">Nome completo</label>
          <input type="text" name="nome" :required="modo === 'local'">
          <div v-if="modo === 'ad'" class="dica">Se ficar em branco, o nome vem do AD.</div>
        </div>
        <div class="campo">
          <label class="obrigatorio">{{ modo === 'ad' ? 'Seu login de rede' : 'Usuário desejado' }}</label>
          <input type="text" name="username" required>
        </div>
        <div v-if="modo === 'local'" class="campo">
          <label class="obrigatorio">Senha</label>
          <input type="password" name="senha" required>
          <div class="dica">Mínimo de 8 caracteres, com letras e números.</div>
        </div>
        <div class="grade grade-2">
          <div class="campo"><label>E-mail</label><input type="email" name="email"></div>
          <div class="campo"><label>Setor</label><input type="text" name="setor"></div>
        </div>
        <div class="campo">
          <label>Perfil pretendido</label>
          <select name="papel">
            <option v-for="(rotulo, codigo) in papeis" :key="codigo" :value="codigo">{{ rotulo }}</option>
          </select>
          <div class="dica">O administrador confirma o perfil ao liberar o acesso.</div>
        </div>
        <button class="botao" style="width:100%" :disabled="loading">Enviar solicitação</button>
      </form>

      <!-- Esqueci a senha (só no modo local; com AD a senha é a da rede) -->
      <form v-else-if="aba === 'senha'" @submit.prevent="enviar('/api/solicitar-senha', $event)">
        <div class="campo"><label class="obrigatorio">Usuário</label><input type="text" name="username" required></div>
        <div class="campo"><label>E-mail cadastrado</label><input type="email" name="email"></div>
        <div class="campo">
          <label class="obrigatorio">Nova senha desejada</label>
          <input type="password" name="senha" required>
          <div class="dica">A senha só passa a valer depois da aprovação do administrador.</div>
        </div>
        <div class="campo"><label>Observação</label><input type="text" name="observacao"></div>
        <button class="botao" style="width:100%" :disabled="loading">Solicitar redefinição</button>
      </form>
    </Card>

    <!-- Rodapé de Versão -->
    <div class="mt-6 text-center text-xs text-slate-500 space-y-1">
      <p class="font-semibold text-slate-700">{{ HOSPITAL_NAME }}</p>
      <p class="text-slate-500">{{ DEPARTMENT_NAME }} | {{ APP_NAME }} versão {{ APP_VERSION }}</p>
      <p class="text-slate-500">Desenvolvido por {{ AUTHOR }}</p>
      <p class="text-slate-500">Suporte: <a :href="`mailto:${SUPPORT_EMAIL}`" style="color:#0F766E;text-decoration:underline">{{ SUPPORT_EMAIL }}</a></p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import axios from 'axios';
import { useAuthStore } from '../stores/auth';
import Card from '../components/Card.vue';
import { ArrowRightOnRectangleIcon, EyeIcon, EyeSlashIcon } from '@heroicons/vue/24/outline';
import { APP_VERSION, APP_NAME, AUTHOR, SUBTITLE, HOSPITAL_NAME, DEPARTMENT_NAME, SUPPORT_EMAIL } from '../config/version';

const username = ref('');
const password = ref('');
const rememberMe = ref(false);
const loading = ref(false);
const passwordVisible = ref(false);
const aba = ref<'entrar' | 'cadastro' | 'senha'>('entrar');
const modo = ref<'ad' | 'local'>('local');
const papeis = ref<Record<string, string>>({});
const mensagem = ref<{ ok: boolean; texto: string; tipo?: string } | null>(null);

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const passwordFieldType = computed(() => passwordVisible.value ? 'text' : 'password');

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/auth/modo');
    modo.value = data.modo;
    papeis.value = data.papeis;
  } catch { /* mantém o modo local */ }
});

function trocar(nova: 'entrar' | 'cadastro' | 'senha') {
  aba.value = nova;
  mensagem.value = null;
}

const handleLogin = async () => {
  loading.value = true;
  mensagem.value = null;
  try {
    await authStore.login(username.value, password.value, rememberMe.value);
    const proximo = String(route.query.proximo || '/');
    await router.push(proximo.startsWith('/') && !proximo.startsWith('//') ? proximo : '/');
  } catch (e: any) {
    const detalhe = e.response?.data?.detail;
    if (detalhe && typeof detalhe === 'object' && detalhe.solicitacao_acesso) {
      // Login confirmado no AD, sem perfil: a solicitação de acesso foi para o administrador.
      mensagem.value = { ok: true, tipo: 'info', texto: detalhe.mensagem };
      password.value = '';
    } else {
      mensagem.value = { ok: false, texto: (typeof detalhe === 'string' ? detalhe : '') || e.message || 'Não foi possível entrar.' };
    }
  } finally {
    loading.value = false;
  }
};

async function enviar(url: string, evento: Event) {
  const form = evento.target as HTMLFormElement;
  loading.value = true;
  mensagem.value = null;
  try {
    const { data } = await axios.post(url, new FormData(form));
    mensagem.value = { ok: !!data.ok, texto: data.mensagem };
    if (data.ok) form.reset();
  } catch (e: any) {
    mensagem.value = { ok: false, texto: e.response?.data?.detail || 'Falha de conexão.' };
  } finally {
    loading.value = false;
  }
}
</script>
